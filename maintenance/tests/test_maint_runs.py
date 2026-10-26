"""A run: work on a project until N% of its functions are matched (or a budget is spent), and be able to continue it later without redoing or re-paying for anything.

The definitions, as decided by the owner:
  - total = the functions open when the run starts, fixed for the life of the run (also across resumes). A work unit is one of them; it is completed when it is matched.
  - `--until N%` (1 to 100) stops gracefully once N% of the total are completed: not N% of the time or of the budget. `--until-budget` is a separate, optional limit.
  - resume = continue from the last committed checkpoint, skip what is completed, start fresh if there is no checkpoint. The checkpoint is the database itself (a match is
    committed the moment it happens), so resuming cannot redo or re-charge a completed function: the run's record only says what is being resumed.
The controller is tested with a real database and three fake callables (start the agents, halt them, count the active ones), so no agent runs and every rule is exact.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from decompnet.app import runs
from decompnet.app.engine import RomNetwork
from decompnet.store import SCHEMA_VERSION, Store

FIXTURE = Path(__file__).parent / "fixtures" / "db-0.10.6.sqlite"


class FakeAgents:
    """What the controller is given instead of real agents."""

    def __init__(self):
        self.started: list[tuple[str, dict]] = []
        self.halted: list[str] = []
        self.working = 1
        self.fail: Exception | None = None

    def launch(self, slug, spec):
        if self.fail:
            raise self.fail
        self.started.append((slug, spec))
        self.working = 1  # new agents are working
        return [f"s{len(self.started)}"]

    def halt(self, slug):
        self.halted.append(slug)
        self.working = 0

    def active(self, slug):
        return self.working


@pytest.fixture
def box(tmp_path):
    """A controller whose watching thread sleeps for an hour: the tests drive `tick` by hand, so nothing happens behind their back. It is shut down after each test."""
    net = RomNetwork(tmp_path / "t.db", tmp_path)
    net.store.conn.execute("INSERT INTO projects(slug, root, config) VALUES ('game', '/x', '{}')")
    agents = FakeAgents()
    ctl = runs.RunController(net, agents.launch, agents.halt, agents.active, poll=3600)
    yield net, agents, ctl
    ctl.shutdown()


def fast(net, agents):
    """A controller that looks every 10 ms: for the tests of the watching thread itself."""
    return runs.RunController(net, agents.launch, agents.halt, agents.active, poll=0.01)


def functions(net, n, status="open", start=0):
    for i in range(start, start + n):
        net.store.conn.execute("INSERT INTO functions(project_id, name, status) VALUES (1, ?, ?)", (f"f{i}", status))


def match(net, *names):
    for name in names:
        net.store.conn.execute("UPDATE functions SET status='matched' WHERE name=?", (name,))


def spec(**kw):
    return {"kind": "claude", "count": 2, **kw}


# ---- what --until accepts --------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text, value", [("50", 50), ("50%", 50), (" 7 % ", 7), (100, 100), ("1", 1), (33, 33)])
def test_until_takes_a_whole_percentage_from_1_to_100(text, value):
    assert runs.parse_until(text) == value


@pytest.mark.parametrize("bad", [0, 101, "0%", "101", "abc", "", "-5", "50.5", True, None, "5 0", "%"])
def test_anything_else_is_refused_with_a_sentence(bad):
    with pytest.raises(runs.RunError, match="from 1 to 100"):
        runs.parse_until(bad)


# ---- starting ---------------------------------------------------------------------------------------------------------------------------------------


def test_a_run_counts_only_the_functions_open_at_the_start_and_records_what_it_needs_to_resume(box):
    net, agents, ctl = box
    functions(net, 8)
    functions(net, 2, status="matched", start=8)  # already done: not part of this run's total
    net.add_spend("game", 1.5, 100, provider="x", agent="a")
    st = ctl.start("game", spec(), until=50)
    assert (st["state"], st["total"], st["completed"], st["until"], st["target"]) == ("running", 8, 0, 50, 4)
    assert agents.started == [("game", spec())]
    row = net.store.one("SELECT * FROM runs")
    assert len(json.loads(row["queue"])) == 8 and row["spend_at_start"] == 1.5 and json.loads(row["spec"])["kind"] == "claude"


@pytest.mark.parametrize("total, until, target", [(10, 25, 3), (10, 100, 10), (3, 1, 1), (1, 1, 1), (7, 50, 4), (200, 33, 66), (10, 10, 1)])
def test_the_target_is_the_percentage_of_the_start_of_run_total_rounded_up(box, total, until, target):
    net, _, ctl = box
    functions(net, total)
    assert ctl.start("game", spec(), until=until)["target"] == target


def test_without_until_the_target_is_every_function(box):
    net, _, ctl = box
    functions(net, 5)
    st = ctl.start("game", spec())
    assert st["until"] is None and st["target"] == 5


def test_a_project_with_nothing_open_is_complete_at_once_and_starts_no_agents(box):
    net, agents, ctl = box
    functions(net, 3, status="matched")
    st = ctl.start("game", spec(), until=50)
    assert st["state"] == "complete" and st["total"] == 0 and agents.started == [] and "nothing" in st["note"]


# ---- finishing --------------------------------------------------------------------------------------------------------------------------------------


def test_it_stops_the_agents_when_the_percentage_is_reached_and_saves_where_it_got_to(box):
    net, agents, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until=30)
    match(net, "f0", "f1")
    assert ctl.tick("game")["state"] == "running"  # 2 of the 3 needed
    match(net, "f2", "f3")  # a tick can overshoot: agents matched another before it looked
    done = ctl.tick("game")
    assert done["state"] == "complete" and done["completed"] == 4 and agents.halted == ["game"]
    assert "30%" in done["note"] and net.store.one("SELECT completed, state FROM runs")["completed"] == 4
    assert ctl.tick("game")["state"] == "complete" and agents.halted == ["game"]  # finished is finished: no second halt


def test_what_counts_is_the_start_of_run_queue_not_functions_that_appear_or_are_matched_outside_it(box):
    net, _, ctl = box
    functions(net, 4)
    ctl.start("game", spec(), until=100)
    functions(net, 3, start=100)  # new functions appear later
    match(net, "f100", "f101")  # and get matched: they are not this run's work
    assert ctl.tick("game")["completed"] == 0
    match(net, "f0")  # one of the queue, matched by someone else (a teammate, the autopilot): counts
    assert ctl.tick("game")["completed"] == 1


def test_all_of_the_queue_matched_is_complete_with_or_without_a_percentage(box):
    net, _, ctl = box
    functions(net, 3)
    ctl.start("game", spec())
    match(net, "f0", "f1", "f2")
    assert ctl.tick("game")["state"] == "complete"


def test_the_agents_giving_up_by_themselves_is_reported_as_ended_with_how_far_it_got(box):
    net, agents, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until=80)
    match(net, "f0", "f1", "f2")
    agents.working = 0  # they all stopped on their own
    st = ctl.tick("game")
    assert st["state"] == "ended" and st["completed"] == 3 and "3 of 10" in st["note"] and "--resume" in st["note"]


def test_when_the_app_knows_why_the_agents_stopped_the_note_says_so_and_when_it_does_not_it_does_not_invent_a_reason(box):
    net, agents, _ = box
    functions(net, 6)
    knowing = runs.RunController(net, agents.launch, agents.halt, agents.active, explain=lambda slug: "Claude Code isn't signed in on this computer", poll=3600)
    knowing.start("game", spec(), until=100)
    agents.working = 0
    note = knowing.tick("game")["note"]
    assert "stopped on their own with 0 of 6 matched" in note and "Last error: Claude Code isn't signed in on this computer" in note and "--resume" in note
    knowing.shutdown()
    net.store.conn.execute("DELETE FROM runs")
    silent = runs.RunController(net, agents.launch, agents.halt, agents.active, explain=lambda slug: "", poll=3600)
    silent.start("game", spec(), until=100)
    agents.working = 0
    assert "Last error" not in silent.tick("game")["note"]
    silent.shutdown()


# ---- the budget -------------------------------------------------------------------------------------------------------------------------------------


def test_until_budget_counts_what_this_run_spent_not_what_the_project_had_spent_before(box):
    net, agents, ctl = box
    functions(net, 10)
    net.add_spend("game", 5.0, 1, provider="x", agent="a")  # spent before the run: does not count against its budget
    ctl.start("game", spec(), until_budget=1.0)
    net.add_spend("game", 0.6, 1, provider="x", agent="a")
    assert ctl.tick("game")["state"] == "running"
    net.add_spend("game", 0.5, 1, provider="x", agent="a")
    st = ctl.tick("game")
    assert st["state"] == "budget" and st["spent"] == pytest.approx(1.1) and agents.halted == ["game"] and "$1" in st["note"]


def test_a_percentage_and_a_budget_together_stop_at_whichever_comes_first(box):
    net, _, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until=50, until_budget=100.0)
    match(net, "f0", "f1", "f2", "f3", "f4")
    assert ctl.tick("game")["state"] == "complete"


def test_a_bad_budget_is_refused(box):
    net, _, ctl = box
    functions(net, 2)
    for bad in (0, -1, "lots", float("nan"), True):
        with pytest.raises(runs.RunError, match="budget"):
            ctl.start("game", spec(), until_budget=bad)


# ---- stopping and resuming --------------------------------------------------------------------------------------------------------------------------


def test_a_person_stopping_it_saves_what_was_done_and_halts_the_agents(box):
    net, agents, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until=100)
    match(net, "f0", "f1", "f2")  # matched since the last look
    st = ctl.stop("game")
    assert st["state"] == "stopped" and st["completed"] == 3 and agents.halted == ["game"]


def test_resuming_continues_the_same_run_skips_what_is_done_and_keeps_the_original_total(box):
    net, agents, ctl = box
    functions(net, 10)
    first = ctl.start("game", spec(count=3, model="m"), until=60)
    queue = net.store.one("SELECT queue FROM runs")["queue"]  # what the run was given at the start
    match(net, "f0", "f1")
    ctl.stop("game")
    match(net, "f2")  # done meanwhile by someone else
    again = ctl.start("game", {}, resume=True)
    assert again["id"] == first["id"] and again["total"] == 10 and again["completed"] == 3 and again["state"] == "running" and again["resumes"] == 1
    assert agents.started[-1] == ("game", spec(count=3, model="m"))  # the stored way of working, as it was
    assert net.store.one("SELECT COUNT(*) AS n FROM runs")["n"] == 1
    assert net.store.one("SELECT queue FROM runs")["queue"] == queue and len(json.loads(queue)) == 10  # stopping and resuming never changes the queue


def test_resume_can_change_the_target_or_the_agents(box):
    net, agents, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until=20)
    ctl.stop("game")
    st = ctl.start("game", spec(kind="codex", count=1), until=70, resume=True)
    assert st["until"] == 70 and st["target"] == 7 and agents.started[-1][1]["kind"] == "codex"


def test_resuming_a_run_whose_target_is_already_met_finishes_it_without_starting_anything(box):
    net, agents, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until=30)
    ctl.stop("game")
    match(net, "f0", "f1", "f2")
    before = len(agents.started)
    st = ctl.start("game", {}, resume=True)
    assert st["state"] == "complete" and len(agents.started) == before and "already" in st["note"]


def test_resuming_with_no_earlier_run_starts_fresh_and_says_so(box):
    net, agents, ctl = box
    functions(net, 6)
    st = ctl.start("game", spec(), until=50, resume=True)
    assert st["state"] == "running" and st["total"] == 6 and "no earlier run" in st["note"] and len(agents.started) == 1


def test_resuming_a_finished_run_is_a_new_run_not_a_second_go_at_the_old_one(box):
    net, _, ctl = box
    functions(net, 4)
    ctl.start("game", spec(), until=25)
    match(net, "f0")
    assert ctl.tick("game")["state"] == "complete"
    st = ctl.start("game", spec(), until=50, resume=True)
    assert st["total"] == 3 and "no earlier run" in st["note"]  # the open functions now, 3 of them


def test_the_budget_of_a_run_is_not_reset_by_resuming_it(box):
    net, _, ctl = box
    functions(net, 10)
    ctl.start("game", spec(), until_budget=1.0)
    net.add_spend("game", 0.7, 1, provider="x", agent="a")
    ctl.stop("game")
    st = ctl.start("game", {}, resume=True)
    assert st["spent"] == pytest.approx(0.7)  # counted from the original start
    net.add_spend("game", 0.4, 1, provider="x", agent="a")
    assert ctl.tick("game")["state"] == "budget"


def test_resuming_changes_nobodys_spend_and_resuming_twice_in_a_row_is_refused_not_repeated(box):
    net, agents, ctl = box
    functions(net, 5)
    ctl.start("game", spec(), until=100)
    net.add_spend("game", 0.3, 10, provider="x", agent="a")
    ctl.stop("game")
    spend = net.spend("game")
    ctl.start("game", {}, resume=True)
    assert net.spend("game") == spend  # the controller never charges anything
    with pytest.raises(runs.RunError, match="already"):
        ctl.start("game", {}, resume=True)
    assert len(agents.started) == 2


def test_starting_a_new_run_over_an_unfinished_one_replaces_it_and_never_leaves_two_running(box):
    net, _, ctl = box
    functions(net, 6)
    old = ctl.start("game", spec(), until=100)
    ctl.stop("game")
    new = ctl.start("game", spec(), until=50)
    assert new["id"] != old["id"]
    assert net.store.one("SELECT state FROM runs WHERE id=?", old["id"])["state"] == "superseded"
    assert net.store.one("SELECT COUNT(*) AS n FROM runs WHERE state='running'")["n"] == 1
    with pytest.raises(runs.RunError, match="already"):
        ctl.start("game", spec())


def test_if_the_agents_cannot_be_started_the_run_says_so_and_nothing_is_left_running(box):
    net, agents, ctl = box
    functions(net, 3)
    agents.fail = ValueError("no such agent: codex")
    with pytest.raises(runs.RunError, match="no such agent"):
        ctl.start("game", spec(kind="codex"))
    assert net.store.one("SELECT state FROM runs")["state"] == "ended" and ctl.status("game")["state"] == "ended"
    agents.fail = None
    assert ctl.start("game", spec())["state"] == "running"  # and it can be tried again


def test_an_unknown_project_is_refused(box):
    _, _, ctl = box
    with pytest.raises(Exception, match="nope"):
        ctl.start("nope", spec())


# ---- after the app stops or crashes -------------------------------------------------------------------------------------------------------------------


def test_a_run_found_running_at_start_up_is_marked_interrupted_and_can_be_resumed(box):
    net, agents, ctl = box
    functions(net, 6)
    ctl.start("game", spec(), until=100)
    match(net, "f0", "f1")
    other = runs.RunController(net, agents.launch, agents.halt, agents.active, poll=3600)  # a new process: the old one died, with no chance to flush
    assert other.recover() == 1
    st = other.status("game")
    assert st["state"] == "interrupted" and st["completed"] == 2 and "--resume" in st["note"]
    assert other.start("game", {}, resume=True)["state"] == "running"


def test_a_normal_shutdown_flushes_the_checkpoint_and_marks_it_interrupted(box):
    net, _, ctl = box
    functions(net, 6)
    ctl.start("game", spec(), until=100)
    match(net, "f0")
    ctl.shutdown()
    assert ctl.status("game")["state"] == "interrupted" and ctl.status("game")["completed"] == 1


def test_the_background_loop_finishes_the_run_by_itself_and_stops_its_thread(box):
    net, agents, _ = box
    ctl = fast(net, agents)
    functions(net, 6)
    ctl.start("game", spec(), until=50)
    thread = ctl._threads["game"]
    match(net, "f0", "f1", "f2")
    deadline = time.time() + 5
    while time.time() < deadline and ctl.status("game")["state"] == "running":
        time.sleep(0.02)
    assert ctl.status("game")["state"] == "complete" and agents.halted == ["game"]
    thread.join(timeout=2)
    assert not thread.is_alive()
    ctl.shutdown()


def test_whether_a_run_is_going_is_read_from_its_record_not_from_whether_a_watching_thread_is_still_alive(box):
    """After a stop the old watcher takes a moment to notice. That window is far too small to hit by chance (a first version of this test caught the bug 1 time in 25),
    so the situation is built: a thread that is still alive when the resume arrives."""
    net, _, ctl = box
    functions(net, 4)
    ctl.start("game", spec(), until=100)
    ctl.stop("game")
    gate = threading.Event()
    lingering = threading.Thread(target=gate.wait, daemon=True)
    lingering.start()
    ctl._threads["game"] = lingering  # the old watcher, which has not yet noticed it was told to stop
    try:
        assert ctl.start("game", {}, resume=True)["state"] == "running"
    finally:
        gate.set()


def test_a_crash_inside_the_loop_is_recorded_on_the_run_not_raised_and_the_agents_are_halted(box, monkeypatch):
    net, agents, _ = box
    ctl = fast(net, agents)
    functions(net, 4)
    monkeypatch.setattr(ctl, "tick", lambda slug: (_ for _ in ()).throw(RuntimeError("the database vanished")))
    ctl.start("game", spec())
    deadline = time.time() + 5
    while time.time() < deadline and net.store.one("SELECT state FROM runs")["state"] == "running":
        time.sleep(0.02)
    row = net.store.one("SELECT state, note FROM runs")
    assert row["state"] == "interrupted" and "the database vanished" in row["note"] and agents.halted == ["game"]


# ---- what is shown ----------------------------------------------------------------------------------------------------------------------------------


def test_the_status_is_plain_json_with_the_figures_a_person_wants(box):
    net, _, ctl = box
    assert ctl.status("game") is None
    functions(net, 8)
    ctl.start("game", spec(), until=50)
    match(net, "f0", "f1")
    st = ctl.tick("game")
    json.dumps(st)  # no Path, no datetime: it goes straight to a browser or a script
    assert (st["percent"], st["target"], st["working"], st["slug"]) == (25.0, 4, 1, "game") and {"started_at", "updated_at", "spent", "state"} <= set(st)


# ---- the schema -------------------------------------------------------------------------------------------------------------------------------------


def test_schema_3_adds_the_runs_table_and_a_v2_database_migrates_with_a_copy_kept(tmp_path):
    assert SCHEMA_VERSION >= 3
    path = tmp_path / "d.db"
    Store(path).conn.close()
    con = sqlite3.connect(path)
    assert {r[1] for r in con.execute("PRAGMA table_info(runs)")} >= {"id", "project_id", "started_at", "updated_at", "state", "total", "completed", "until_pct", "until_usd", "spend_at_start", "queue", "spec", "note"}
    con.execute("DROP TABLE runs")
    con.execute("PRAGMA user_version = 2")
    con.commit()
    con.close()
    Store(path).conn.close()
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION and con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert (tmp_path / "d.db.bak-v2").exists()


def test_upstreams_0_10_6_database_still_opens_and_gets_the_table(tmp_path):
    path = tmp_path / "up.db"
    shutil.copy(FIXTURE, path)
    Store(path).conn.close()
    assert sqlite3.connect(path).execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
