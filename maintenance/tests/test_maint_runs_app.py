"""`decomp run`, through the real app (the routes, with fake agent sessions) and through the real command line (against a stand-in for the app's API).

The agents are fakes because the point here is the plumbing and the rules: that the routes are guarded and validate, that the controller sees the app's real session list, that stopping
the app flushes a run so it can be resumed, and that the command says the right thing for every way a run can end. The rules themselves are in test_maint_runs.py.
"""

from __future__ import annotations

import json
import time

import pytest
from starlette.testclient import TestClient

from decompnet.app import agents, bridge, cli, runs
from decompnet.app.engine import RomNetwork
from decompnet.app.server import build

PORT, SECRET = 6496, "s3cret-for-run-tests"
H = {"X-Decomp": "1"}


def functions(net, n, status="open", start=0):
    for i in range(start, start + n):
        net.store.conn.execute("INSERT INTO functions(project_id, name, status) VALUES (1, ?, ?)", (f"f{i}", status))


def match(net, *names):
    for name in names:
        net.store.conn.execute("UPDATE functions SET status='matched' WHERE name=?", (name,))


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "POLL", 0.05)
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    net.store.conn.execute("INSERT INTO projects(slug, root, config) VALUES ('game', '/x', '{}')")
    functions(net, 8)
    return net, home


def serve(net, home, monkeypatch):
    mcp, manager, security = build(net, home / ".decomp", PORT, SECRET)
    started = []

    def fake_start(kind, slug, count=1, options=None):
        ids = []
        for _ in range(count):
            sid = f"fake-{len(manager.sessions) + 1}"
            manager.sessions[sid] = agents.Session(sid, kind, f"{kind} #{sid}", slug, f"agent-{sid}", dict(options or {}))
            manager.sessions[sid].state = "working"
            ids.append(sid)
        started.append((kind, slug, count, dict(options or {})))
        return ids

    monkeypatch.setattr(manager, "start", fake_start)
    client = TestClient(mcp.streamable_http_app(transport_security=security, host="127.0.0.1"), base_url=f"http://127.0.0.1:{PORT}")
    client.cookies.set("decomp_live", SECRET)
    return client, manager, started


def wait_for(client, state, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        run = client.get("/api/run?slug=game").json()["run"]
        if run["state"] == state:
            return run
        time.sleep(0.02)
    return client.get("/api/run?slug=game").json()["run"]


# ---- the routes ---------------------------------------------------------------------------------------------------------------------------------------


def test_starting_a_run_needs_the_header_and_validates_everything_with_a_sentence(app, monkeypatch):
    net, home = app
    client, manager, _ = serve(net, home, monkeypatch)
    try:
        assert client.post("/api/run", json={"slug": "game", "kind": "claude"}).status_code == 403
        assert client.post("/api/run/stop", json={"slug": "game"}).status_code == 403
        for body, text in (({"slug": "game", "kind": "claude", "until": 0}, "from 1 to 100"), ({"slug": "game", "kind": "claude", "until": "abc"}, "from 1 to 100"),
                           ({"slug": "game", "kind": "claude", "until_budget": -1}, "budget"), ({"slug": "nope", "kind": "claude"}, "nope"),
                           ({"slug": "game"}, "choose an agent"), ({"slug": "game", "kind": "skynet"}, "unknown agent")):
            r = client.post("/api/run", json=body, headers=H)
            assert r.status_code == 400 and text in r.text and "Traceback" not in r.text, (body, r.text)
        assert net.store.one("SELECT COUNT(*) AS n FROM runs")["n"] == 0  # a refused request starts nothing
    finally:
        manager.on_stop()


def test_a_run_starts_agents_through_the_same_path_as_the_start_button_and_is_visible_while_it_works(app, monkeypatch):
    net, home = app
    client, manager, started = serve(net, home, monkeypatch)
    try:
        r = client.post("/api/run", json={"slug": "game", "kind": "claude", "count": 2, "model": "sonnet", "until": 50}, headers=H)
        run = r.json()["run"]
        assert r.status_code == 200 and (run["state"], run["total"], run["target"], run["working"]) == ("running", 8, 4, 2)
        assert started[0][:3] == ("claude", "game", 2) and started[0][3]["model"] == "sonnet" and "per_session" in started[0][3]
        assert client.get("/api/run?slug=game").json()["run"]["id"] == run["id"]
        assert client.get("/api/run?slug=nope").status_code == 400
    finally:
        manager.on_stop()


def test_the_run_ends_by_itself_when_the_agents_have_matched_enough_and_the_agents_are_stopped(app, monkeypatch):
    net, home = app
    client, manager, _ = serve(net, home, monkeypatch)
    try:
        client.post("/api/run", json={"slug": "game", "kind": "claude", "until": 25}, headers=H)
        match(net, "f0", "f1")
        run = wait_for(client, "complete")
        assert run["state"] == "complete" and run["completed"] == 2 and "reached 25%" in run["note"]
        assert [s.state for s in manager.sessions.values()] == ["stopped"]  # the app's real stop was used on the app's real sessions
    finally:
        manager.on_stop()


def test_stop_then_resume_carries_on_the_same_run(app, monkeypatch):
    net, home = app
    client, manager, started = serve(net, home, monkeypatch)
    try:
        first = client.post("/api/run", json={"slug": "game", "kind": "claude", "count": 3, "until": 100}, headers=H).json()["run"]
        match(net, "f0", "f1")
        stopped = client.post("/api/run/stop", json={"slug": "game"}, headers=H).json()["run"]
        assert stopped["state"] == "stopped" and stopped["completed"] == 2
        again = client.post("/api/run", json={"slug": "game", "resume": True}, headers=H).json()["run"]
        assert again["id"] == first["id"] and again["state"] == "running" and again["resumes"] == 1 and again["total"] == 8
        assert started[-1][:3] == ("claude", "game", 3)  # the way the agents were started, as it was
    finally:
        manager.on_stop()


def test_stopping_the_app_flushes_a_running_run_as_interrupted_so_it_can_be_resumed(app, monkeypatch):
    net, home = app
    client, manager, _ = serve(net, home, monkeypatch)
    client.post("/api/run", json={"slug": "game", "kind": "claude", "until": 100}, headers=H)
    match(net, "f0", "f1", "f2")
    manager.on_stop()
    row = net.store.one("SELECT state, completed, note FROM runs")
    assert (row["state"], row["completed"]) == ("interrupted", 3) and "--resume" in row["note"]


def test_a_run_left_running_by_an_app_that_died_is_marked_interrupted_when_the_next_app_starts(app, monkeypatch):
    net, home = app
    net.store.conn.execute("INSERT INTO runs(project_id, started_at, updated_at, state, total, queue, spec) VALUES (1, 0, 0, 'running', 8, ?, '{}')",
                           (json.dumps([r["id"] for r in net.store.all("SELECT id FROM functions")]),))
    match(net, "f0")
    client, manager, _ = serve(net, home, monkeypatch)  # a new app: build() recovers
    try:
        run = client.get("/api/run?slug=game").json()["run"]
        assert run["state"] == "interrupted" and run["completed"] == 1
    finally:
        manager.on_stop()


def test_a_run_whose_agent_failed_for_a_reason_the_app_knows_says_that_reason(app, monkeypatch):
    net, home = app
    client, manager, _ = serve(net, home, monkeypatch)
    try:
        client.post("/api/run", json={"slug": "game", "kind": "claude", "until": 100}, headers=H)
        (session,) = manager.sessions.values()
        session.push("error", "claude: command not found")  # what each failed attempt leaves in the session's feed
        session.error, session.state = "the agent failed three times in a row", "error"  # and the summary the session ends with
        run = wait_for(client, "ended")
        assert run["state"] == "ended" and "the agent failed three times in a row; claude: command not found" in run["note"]  # the summary AND the cause
    finally:
        manager.on_stop()


def test_the_start_button_still_works_the_way_it_did(app, monkeypatch):
    net, home = app
    client, manager, started = serve(net, home, monkeypatch)
    try:
        r = client.post("/api/agents/start", json={"kind": "claude", "slug": "game", "count": 2, "options": {"model": "m"}}, headers=H)
        assert r.status_code == 200 and len(r.json()["started"]) == 2 and started[0][:3] == ("claude", "game", 2)
        assert client.post("/api/agents/start", json={"kind": "claude", "slug": "nope"}, headers=H).status_code == 400
    finally:
        manager.on_stop()


# ---- the command ---------------------------------------------------------------------------------------------------------------------------------------


class Agents:
    def __init__(self):
        self.started, self.working = [], 1

    def launch(self, slug, spec):
        self.started.append(spec)
        self.working = 1  # new agents are working
        return ["s1"]

    def halt(self, slug):
        self.working = 0

    def active(self, slug):
        return self.working


@pytest.fixture
def cmd(tmp_path, monkeypatch, capsys):
    """The command line wired to a real controller instead of an app: its `_api` calls land in the controller, and each `time.sleep` it makes lets the 'agents' match a function."""
    net = RomNetwork(tmp_path / "t.db", tmp_path)
    net.store.conn.execute("INSERT INTO projects(slug, root, config) VALUES ('game', '/x', '{}')")
    functions(net, 10)
    fake = Agents()
    ctl = runs.RunController(net, fake.launch, fake.halt, fake.active, poll=3600)
    world = {"matched": 0, "per_sleep": 1, "steps": [], "spend_per_sleep": 0.0, "interrupt_at": None, "agents_stop_at": None, "sleeps": 0}

    def api(path, body=None):
        try:
            if path == "/api/state":
                return {"projects": [{"slug": "game"}]}
            if path.startswith("/api/run?slug="):
                ctl.tick(path.split("=", 1)[1])
                return {"run": ctl.status(path.split("=", 1)[1])}
            if path == "/api/run/stop":
                return {"run": ctl.stop(body["slug"])}
            if path == "/api/run":
                spec = {k: body[k] for k in ("kind", "count", "model", "endpoints") if body.get(k) not in (None, "", [])}
                return {"run": ctl.start(body["slug"], spec, body.get("until"), body.get("until_budget"), bool(body.get("resume")))}
        except runs.RunError as e:
            raise SystemExit(str(e)) from None
        raise AssertionError(path)

    def sleep(seconds):
        world["sleeps"] += 1
        if world["interrupt_at"] and world["sleeps"] >= world["interrupt_at"]:
            raise KeyboardInterrupt
        if world["agents_stop_at"] and world["sleeps"] >= world["agents_stop_at"]:
            fake.working = 0  # they give up on their own, mid-run
        for _ in range(world["steps"].pop(0) if world["steps"] else world["per_sleep"]):
            world["matched"] += 1
            match(net, f"f{world['matched'] - 1}")
        if world["spend_per_sleep"]:
            net.add_spend("game", world["spend_per_sleep"], 1, provider="x", agent="a")

    monkeypatch.setattr(cli, "_api", api)
    monkeypatch.setattr(bridge, "ensure_app", lambda home: {})
    monkeypatch.setattr(cli.time, "sleep", sleep)
    monkeypatch.setenv("DECOMP_HOME", str(tmp_path))
    yield cli, fake, world, net, ctl, capsys
    ctl.shutdown()


def run_cli(cmd, *argv):
    cli_, _, _, _, _, capsys = cmd
    code = cli_.main(["run", *argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_it_follows_a_run_to_the_percentage_and_says_what_it_reached(cmd):
    code, out, _ = run_cli(cmd, "game", "--until", "40%", "--agent", "claude", "--count", "2")
    assert code == 0
    assert "Running game until 40% (4 of 10 functions)" in out and "4 of 10 matched (40%)" in out and "reached 40%: 4 of 10 functions matched" in out
    assert cmd[1].started == [{"kind": "claude", "count": 2}]


def test_the_progress_is_printed_when_it_changes_not_at_every_look(cmd):
    cmd[2]["steps"] = [0, 0, 3, 0, 7]  # five looks: nothing, nothing, three matched, nothing, the rest
    _, out, _ = run_cli(cmd, "game", "--until", "100", "--agent", "claude")
    lines = [l for l in out.splitlines() if l.startswith("  ")]
    assert lines == ["  0 of 10 matched (0%) (target 10, 100%) · $0.00 spent · 1 agent working",
                     "  3 of 10 matched (30%) (target 10, 100%) · $0.00 spent · 1 agent working",
                     "  10 of 10 matched (100%) (target 10, 100%) · $0.00 spent"]
    assert cmd[2]["sleeps"] == 5


def test_it_ends_on_the_budget_and_says_how_to_carry_on(cmd):
    cmd[2]["spend_per_sleep"] = 0.4
    code, out, _ = run_cli(cmd, "game", "--until-budget", "1", "--agent", "claude")
    assert code == 0 and "budget of $1 was reached" in out and "--resume" in out


def test_the_agents_stopping_by_themselves_is_a_failure_exit_that_says_how_far_it_got(cmd):
    cmd[2]["agents_stop_at"] = 2
    cmd[2]["per_sleep"] = 1
    code, out, _ = run_cli(cmd, "game", "--until", "50", "--agent", "claude")
    assert code == 1 and "stopped on their own with 2 of 10 matched" in out and "--resume" in out


def test_ctrl_c_stops_the_run_saves_where_it_got_to_and_says_how_to_resume(cmd):
    cmd[2]["interrupt_at"] = 3
    code, out, _ = run_cli(cmd, "game", "--until", "100", "--agent", "claude")
    assert code == 130 and "stopped." in out and "--resume" in out
    assert cmd[4].status("game")["state"] == "stopped" and cmd[4].status("game")["completed"] == 2


def test_resume_carries_on_a_stopped_run_and_without_one_it_says_it_is_starting_fresh(cmd):
    code, out, _ = run_cli(cmd, "game", "--resume", "--until", "20", "--agent", "claude")
    assert "no earlier run to resume: starting a new one." in out and code == 0
    cmd[2]["interrupt_at"] = cmd[2]["sleeps"] + 1
    cmd[2]["matched"], cmd[2]["interrupt_at"] = 2, None
    cmd[4].start("game", {"kind": "claude"}, until=60)
    cmd[4].stop("game")
    code, out, _ = run_cli(cmd, "game", "--resume")
    assert "resumed at" in out and "reached 60%" in out and code == 0


def test_detach_starts_the_run_and_returns_at_once_and_status_and_stop_work(cmd):
    code, out, _ = run_cli(cmd, "game", "--until", "50", "--agent", "claude", "--detach")
    assert code == 0 and "Running game until 50%" in out and cmd[2]["sleeps"] == 0
    code, out, _ = run_cli(cmd, "game", "--status")
    assert code == 0 and out.startswith("running: 0 of 10 matched")
    code, out, _ = run_cli(cmd, "game", "--stop")
    assert code == 0 and "stopped at 0 of 10" in out


def test_a_bad_percentage_or_budget_is_refused_before_anything_is_started(cmd):
    for argv in (("game", "--until", "0"), ("game", "--until", "150%"), ("game", "--until", "half"), ("game", "--until-budget", "-3"), ("game", "--until-budget", "lots")):
        code, out, err = run_cli(cmd, *argv)
        assert code == 2 and err.startswith("error: ") and "Traceback" not in err, argv
    assert cmd[1].started == [] and cmd[4].status("game") is None


def test_a_project_that_does_not_exist_is_refused_naming_the_projects_that_do(cmd):
    with pytest.raises(SystemExit) as refused:
        cmd[0].main(["run", "nope", "--agent", "claude"])
    assert str(refused.value) == "no project 'nope'; projects here: game" and cmd[4].status("game") is None


def test_the_project_may_be_left_out_when_there_is_only_one(cmd):
    code, out, _ = run_cli(cmd, "--until", "10", "--agent", "claude")
    assert code == 0 and "Running game until 10% (1 of 10 functions)" in out


def test_a_second_run_while_one_is_going_is_refused_with_a_sentence(cmd):
    run_cli(cmd, "game", "--until", "50", "--agent", "claude", "--detach")
    with pytest.raises(SystemExit, match="already going"):
        cmd[0].main(["run", "game", "--until", "50", "--agent", "claude"])
