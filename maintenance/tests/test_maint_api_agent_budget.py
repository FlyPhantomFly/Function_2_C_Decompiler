"""The project budget (Settings, in US dollars) must be able to stop an API agent, and must do so mid-session.

The budget was only ever fed by agents that report dollars (Claude Code and the like). The built-in API agent recorded `{"tokens": ...}` and
nothing else, so its spend stayed at $0 and the cap could never fire for exactly the agents that bill per token. And the cap was only looked at
between sessions, so a session of up to 120 steps could spend past it. Now the cost a provider reports (OpenRouter puts `cost` in `usage`) is
recorded, and the budget is checked before every request. A provider that reports no cost is unchanged: tokens only, and the budget does not apply.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from decompnet.app import agents


class FakeStop:
    def wait(self, seconds):
        return False

    def is_set(self):
        return False


def reply(usage=None, tool=True):
    msg = {"role": "assistant", "content": None if tool else "done"}
    if tool:
        msg["tool_calls"] = [{"id": "1", "type": "function", "function": {"name": "project_info", "arguments": "{}"}}]
    body = {"choices": [{"message": msg}]}
    if usage is not None:
        body["usage"] = usage
    # json.dumps, not httpx's json=: httpx refuses NaN, and a sloppy provider can send it
    return httpx.Response(200, content=json.dumps(body).encode(), headers={"content-type": "application/json"})


class Ledger:
    """The project's spend as the network would keep it."""

    def __init__(self):
        self.usd, self.tokens, self.calls = 0.0, 0, []

    def add_spend(self, slug, usd, tokens, **tags):
        self.usd += usd
        self.tokens += tokens
        self.calls.append((slug, usd, tokens))

    def spend(self, slug):
        return {"usd": self.usd, "tokens": self.tokens}


def run(monkeypatch, replies, *, budget=0.0, max_steps=120):
    ledger, seen = Ledger(), []
    manager = agents.Manager.__new__(agents.Manager)
    manager.net = SimpleNamespace(fork_slug=lambda slug: None, add_spend=ledger.add_spend, spend=ledger.spend)
    manager.prompt = lambda s: "go"
    manager.budget = lambda: budget
    monkeypatch.setattr(agents.tools, "call", lambda net, agent, slug, name, args: "ok")
    script = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return script.pop(0) if len(script) > 1 else script[0]

    real = httpx.Client
    monkeypatch.setattr(agents.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    s = agents.Session("api-b", "api", "Test", "demo", "api-test", {"base_url": "http://8.8.8.8/v1", "model": "m", "max_steps": max_steps})
    s.stop = FakeStop()
    result = manager._run_api(s, SimpleNamespace(id=1))
    return s, ledger, seen, result


# ---- the cost a provider reports is recorded --------------------------------------------------------------------------------------------


def test_a_cost_the_provider_reports_is_recorded_in_dollars_with_the_tokens(monkeypatch):
    s, ledger, _, _ = run(monkeypatch, [reply({"total_tokens": 500, "cost": 0.0123}, tool=False)])
    assert ledger.calls == [("demo", 0.0123, 500)] and s.usd == pytest.approx(0.0123) and s.tokens == 500


def test_a_usage_without_a_cost_records_tokens_only_as_before(monkeypatch):
    s, ledger, _, _ = run(monkeypatch, [reply({"total_tokens": 500}, tool=False)])
    assert ledger.calls == [("demo", 0.0, 500)] and s.usd == 0.0


@pytest.mark.parametrize("cost", ["free", "0.02", None, -0.5, 0, float("nan"), float("inf"), [1], {"a": 1}, True, False])
def test_a_cost_that_is_not_a_positive_finite_number_is_ignored_never_trusted(monkeypatch, cost):
    """Only a real number counts. JSON `true` is a boolean, and float(True) is 1.0: a naive parse would book a dollar."""
    _, ledger, _, _ = run(monkeypatch, [reply({"total_tokens": 10, "cost": cost}, tool=False)])
    assert ledger.usd == 0.0 and ledger.tokens == 10


def test_a_provider_that_gives_a_cost_but_no_token_count_still_has_its_dollars_recorded(monkeypatch):
    _, ledger, _, _ = run(monkeypatch, [reply({"cost": 0.02}, tool=False)])
    assert ledger.usd == pytest.approx(0.02) and ledger.tokens == 0


def test_no_usage_at_all_records_nothing(monkeypatch):
    _, ledger, _, _ = run(monkeypatch, [reply(None, tool=False)])
    assert ledger.calls == []


# ---- the budget is looked at before every request ---------------------------------------------------------------------------------------


def test_the_budget_ends_a_session_in_the_middle_not_after_its_last_step(monkeypatch):
    s, ledger, seen, result = run(monkeypatch, [reply({"total_tokens": 100, "cost": 0.02})], budget=0.05)
    assert len(seen) == 3 and ledger.usd == pytest.approx(0.06)  # 0.02, 0.04, 0.06: the fourth request is never sent
    assert result is True  # tools were used, so the run counts as work done: the run loop then reports the budget and stops
    assert any("budget is spent" in f["text"] for f in s.feed)


def test_with_no_budget_set_the_session_runs_its_course(monkeypatch):
    _, ledger, seen, _ = run(monkeypatch, [reply({"total_tokens": 100, "cost": 0.02})], budget=0.0, max_steps=6)
    assert len(seen) == 6 and ledger.usd == pytest.approx(0.12)


def test_a_provider_that_reports_no_cost_is_not_stopped_by_a_dollar_budget(monkeypatch):
    _, ledger, seen, _ = run(monkeypatch, [reply({"total_tokens": 100})], budget=0.05, max_steps=5)
    assert len(seen) == 5 and ledger.usd == 0.0  # the budget cannot see what it was not told: documented, not hidden


def test_a_budget_already_spent_stops_the_session_before_the_first_request(monkeypatch):
    ledger_start = Ledger()
    ledger_start.usd = 1.0
    manager = agents.Manager.__new__(agents.Manager)
    manager.net = SimpleNamespace(fork_slug=lambda slug: None, add_spend=ledger_start.add_spend, spend=ledger_start.spend)
    manager.prompt = lambda s: "go"
    manager.budget = lambda: 0.5
    seen = []
    real = httpx.Client
    monkeypatch.setattr(agents.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(lambda r: seen.append(r) or reply(None, tool=False)), **kw))
    s = agents.Session("api-b", "api", "Test", "demo", "api-test", {"base_url": "http://8.8.8.8/v1", "model": "m"})
    s.stop = FakeStop()
    manager._run_api(s, SimpleNamespace(id=1))
    assert seen == []
