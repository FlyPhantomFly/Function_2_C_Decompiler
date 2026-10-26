"""A blip between the app and the model's server must not cost the agent its conversation.

The built-in API agent used to send each request once. A connection reset or a timeout raised out of the loop, a 502/503/504 returned
"failed", and a 429 restarted the whole session a minute later; each of those threw away the conversation, counted as a failure, and
three in a row stopped the agent. Now a request is retried in place, with backoff, when the failure is plausibly transient, and never
when retrying would be wrong (a bad request, a refused key, "out of credit", "context too long"). The helper is tested alone, with a
scripted server and a fake clock, and then through the real agent loop.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from decompnet.app import agents

URL = "http://mock/v1/chat/completions"
REMOTE = "http://8.8.8.8/v1"  # a public address: not a local server (is_local counts any dotless name, such as `mock`, as one), never contacted
OK = {"choices": [{"message": {"role": "assistant", "content": "done"}}]}


class FakeStop:
    """A stop flag that records how long it was asked to wait and never really waits."""

    def __init__(self, set_on_wait: int | None = None):
        self.waits: list[float] = []
        self._set = False
        self._set_on_wait = set_on_wait

    def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        if self._set_on_wait is not None and len(self.waits) >= self._set_on_wait:
            self._set = True
        return self._set

    def is_set(self) -> bool:
        return self._set


def serve(*steps):
    """A client whose server answers with each step in turn: an httpx.Response, or an exception to raise. Returns (client, requests)."""
    script, seen = list(steps), []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def post(client, stop, notes=None):
    return agents.post_with_retries(client, URL, headers={}, payload={"n": 1}, stop=stop, note=(notes if notes is not None else []).append)


def reply(status, text="", **headers):
    return httpx.Response(status, text=text, headers=headers)


# ---- what is retried, and how long it waits -------------------------------------------------------------------------------------------


def test_a_good_answer_is_one_request_and_no_waiting():
    client, seen = serve(httpx.Response(200, json=OK))
    stop = FakeStop()
    assert post(client, stop).status_code == 200 and len(seen) == 1 and stop.waits == []


def test_a_transient_error_is_retried_with_a_doubling_backoff_and_the_agent_is_told():
    client, seen = serve(reply(503), reply(502), reply(504), httpx.Response(200, json=OK))
    stop, notes = FakeStop(), []
    r = post(client, stop, notes)
    assert r.status_code == 200 and len(seen) == 4 and seen[0] == seen[3] == {"n": 1}  # the same request each time
    assert stop.waits == [2, 4, 8]
    assert "503" in notes[0] and "trying again in 2s" in notes[0] and "504" in notes[2]


def test_the_server_is_obeyed_when_it_says_how_long_to_wait_but_never_for_more_than_two_minutes():
    client, _ = serve(reply(429, "slow down", **{"Retry-After": "7"}), reply(429, "slow down", **{"Retry-After": "99999"}), httpx.Response(200, json=OK))
    stop = FakeStop()
    assert post(client, stop).status_code == 200
    assert stop.waits == [7, 120]


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("reset")])
def test_a_network_failure_is_retried(error):
    client, seen = serve(error, httpx.Response(200, json=OK))
    stop, notes = FakeStop(), []
    assert post(client, stop, notes).status_code == 200 and len(seen) == 2 and stop.waits == [2]
    assert type(error).__name__ in notes[0]


def test_after_five_failed_tries_the_last_answer_is_handed_back_for_the_caller_to_report():
    client, seen = serve(*[reply(503, "busy")] * 5)
    stop = FakeStop()
    r = post(client, stop)
    assert r.status_code == 503 and len(seen) == 5 and stop.waits == [2, 4, 8, 16]


def test_after_five_network_failures_the_error_is_raised_as_before():
    client, seen = serve(*[httpx.ConnectError("refused")] * 5)
    with pytest.raises(httpx.ConnectError):
        post(client, FakeStop())
    assert len(seen) == 5


# ---- what is never retried ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status, text", [
    (400, "bad request"), (401, "invalid api key"), (403, "forbidden"), (404, "no such model"), (402, "payment required"),
    (429, '{"error": {"code": "insufficient_quota", "message": "You exceeded your current quota, please check your plan and billing"}}'),
    (500, "This model's maximum context length is 8192 tokens. However, you requested 20000 tokens"),
    (400, "maximum context length is 4096 tokens"),
])
def test_an_answer_that_retrying_cannot_change_is_returned_at_once(status, text):
    client, seen = serve(reply(status, text), httpx.Response(200, json=OK))
    stop = FakeStop()
    assert post(client, stop).status_code == status and len(seen) == 1 and stop.waits == []


def test_a_short_wait_is_not_announced_as_zero_seconds():
    client, _ = serve(reply(503, "busy", **{"Retry-After": "0.3"}), httpx.Response(200, json=OK))
    notes = []
    assert post(client, FakeStop(), notes).status_code == 200
    assert notes == ["the model's server said 503: trying again in 0.3s"]


def test_a_stop_during_a_wait_ends_the_retrying_without_another_request():
    client, seen = serve(reply(503), reply(503), httpx.Response(200, json=OK))
    stop = FakeStop(set_on_wait=1)
    assert post(client, stop) is None and len(seen) == 1


# ---- a local server that is not running ------------------------------------------------------------------------------------------------


def test_a_refused_connection_to_a_local_server_fails_at_once_because_waiting_cannot_start_it():
    client, seen = serve(httpx.ConnectError("refused"), httpx.Response(200, json=OK))
    stop = FakeStop()
    with pytest.raises(httpx.ConnectError):
        agents.post_with_retries(client, URL, headers={}, payload={"n": 1}, stop=stop, note=[].append, retry_connect_errors=False)
    assert len(seen) == 1 and stop.waits == []


def test_a_busy_local_server_is_still_retried_llama_cpp_answers_503_while_it_loads_a_model():
    client, seen = serve(reply(503, "Loading model"), httpx.Response(200, json=OK))
    stop = FakeStop()
    r = agents.post_with_retries(client, URL, headers={}, payload={"n": 1}, stop=stop, note=[].append, retry_connect_errors=False)
    assert r.status_code == 200 and len(seen) == 2 and stop.waits == [2]


def test_through_the_agent_loop_a_local_address_is_not_retried_but_a_remote_one_is(monkeypatch):
    real = httpx.Client  # taken once: patching it twice would wrap the first patch

    def run(base):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":  # the context-window probe a local server gets
                return httpx.Response(404)
            requests.append(request)
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(agents.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
        s = agents.Session("api-l", "api", "Test", "demo", "api-test", {"base_url": base, "model": "m"})
        s.stop = FakeStop()
        with pytest.raises(httpx.ConnectError):
            make_manager()._run_api(s, SimpleNamespace(id=1))
        return len(requests)

    assert run("http://127.0.0.1:11434/v1") == 1 and run("http://ollama:11434/v1") == 1  # this computer, and a dotless name such as a compose service
    assert run(REMOTE) == agents.RETRY_ATTEMPTS


# ---- through the real agent loop --------------------------------------------------------------------------------------------------------


def make_manager():
    manager = agents.Manager.__new__(agents.Manager)
    manager.net = SimpleNamespace(fork_slug=lambda slug: None, add_spend=lambda *a, **k: None, spend=lambda slug: {})
    manager.prompt = lambda s: "decompile something"
    return manager


def session(stop):
    s = agents.Session("api-r", "api", "Test", "demo", "api-test", {"base_url": REMOTE, "model": "m"})
    s.stop = stop
    return s


def test_a_blip_in_the_middle_of_a_session_keeps_the_conversation_and_does_not_count_as_a_failure(monkeypatch):
    seen, script = [], [reply(503), httpx.ConnectError("reset"), httpx.Response(200, json=OK)]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    real = httpx.Client
    monkeypatch.setattr(agents.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    s = session(FakeStop())
    assert make_manager()._run_api(s, SimpleNamespace(id=1)) is False  # the model answered without using a tool: nothing was done, as before
    assert len(seen) == 3 and seen[0]["messages"] == seen[2]["messages"]  # one conversation, sent three times
    assert s.error == ""  # not an error: a session that retried through a blip is not a failed one
    assert [f["text"] for f in s.feed if f["type"] == "info" and "trying again" in f["text"]] == [
        "the model's server said 503: trying again in 2s", "the model's server didn't answer (ConnectError): trying again in 4s"]


def test_a_server_that_stays_down_still_ends_the_session_with_the_error_after_the_retries(monkeypatch):
    real = httpx.Client
    monkeypatch.setattr(agents.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(lambda r: reply(503, "down")), **kw))
    s = session(FakeStop())
    assert make_manager()._run_api(s, SimpleNamespace(id=1)) is False
    assert s.error.startswith("API error 503") and not s.throttled
