"""Runs: work on a project until N% of its functions are matched, and continue later without redoing or re-paying for anything.

`decomp run SLUG --until 50%` starts helper agents on a project and stops them gracefully once half of the project's start-of-run work is done. The definitions (the owner's):

  - **Work units.** The functions that are open when the run starts. That list is the run's queue and its length is the run's total; both are fixed for the life of the run, also
    across resumes. A unit is completed when it is matched, by whoever matched it (an agent of this run, the autopilot, a teammate).
  - **`--until N%`** (a whole number from 1 to 100) stops once at least ceil(total * N / 100) units are completed. It is a share of the work and not of the time or the budget. A
    check can find that agents matched a few more than the target since it last looked, so the run may end slightly past N%.
  - **`--until-budget USD`** is a separate limit: stop once the run has spent that much. It is measured from the run's own start, so resuming does not reset it.
  - **Resume** continues the latest unfinished run (stopped, ended, interrupted or out of budget) from its checkpoint, and starts a new run if there is none.

The checkpoint is the database: a match is committed the moment it happens, so there is nothing to replay. The `runs` row only records what is being resumed (the queue, the target, the
way the agents were started) and the progress at the last flush. That is why resuming cannot redo or re-charge a completed function: completed functions are no longer open, agents
only take open ones, and the controller itself never spends anything.

The controller is told how to start agents, how to halt them and how many are still working, so it is tested without any.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time

log = logging.getLogger("decomp.wtf")

POLL = 3.0  # seconds between looks at a running run
UNFINISHED = ("stopped", "ended", "interrupted", "budget")  # states `resume` can continue
UNTIL_HELP = "--until takes a whole percentage from 1 to 100, like 50 or 50%"


class RunError(ValueError):
    """Something to tell the person in a sentence."""


def parse_until(value) -> int:
    if isinstance(value, bool) or value is None:
        raise RunError(UNTIL_HELP)
    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    if not re.fullmatch(r"\d{1,3}", text) or not 1 <= int(text) <= 100:
        raise RunError(UNTIL_HELP)
    return int(text)


def parse_budget(value) -> float:
    try:
        number = float(value) if not isinstance(value, bool) else float("nan")
    except (TypeError, ValueError):
        number = float("nan")
    if not math.isfinite(number) or number <= 0:
        raise RunError("the budget for a run is a positive number of US dollars, like 5 or 2.50")
    return number


def target_of(total: int, until: int | None) -> int:
    return 0 if total == 0 else (total if not until else max(1, math.ceil(total * until / 100)))


def progress_line(run: dict) -> str:
    """One line of progress, as `decomp run` prints it."""
    target = f" (target {run['target']}, {run['until']}%)" if run.get("until") else ""
    working = f" · {run['working']} agent{'s' if run['working'] != 1 else ''} working" if run["state"] == "running" else ""
    return f"{run['completed']} of {run['total']} matched ({run['percent']:.0f}%){target} · ${run['spent']:.2f} spent{working}"


class RunController:
    def __init__(self, net, launch, halt, active, *, explain=lambda slug: "", clock=time.time, poll: float | None = None):
        """`launch(slug, spec) -> list of session ids`, `halt(slug)` and `active(slug) -> how many agents are still working` are how the controller
        starts, stops and watches the agents; `explain(slug)` says why they failed, if the app knows; `net` is the RomNetwork whose database holds the runs."""
        self.net, self.launch, self.halt, self.active, self.explain = net, launch, halt, active, explain
        self.clock = clock
        self.poll = POLL if poll is None else poll
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._stops: dict[str, threading.Event] = {}

    # ---- the database -----------------------------------------------------------------------------------------------------------------------------------

    def _latest(self, project_id: int):
        return self.net.store.one("SELECT * FROM runs WHERE project_id=? ORDER BY id DESC LIMIT 1", project_id)

    def _save(self, run_id: int, **fields) -> None:
        fields["updated_at"] = self.clock()
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.net.store.tx() as db:
            db.execute(f"UPDATE runs SET {sets} WHERE id=?", (*fields.values(), run_id))

    def _done(self, row) -> int:
        """How many of the run's queue are matched now."""
        return self.net.store.one("SELECT COUNT(*) AS n FROM functions WHERE status='matched' AND id IN (SELECT value FROM json_each(?))", row["queue"])["n"]

    def _spent(self, row, slug: str) -> float:
        return max(0.0, float((self.net.spend(slug) or {}).get("usd", 0)) - row["spend_at_start"])

    def _view(self, row, slug: str) -> dict:
        live = row["state"] == "running"
        completed = self._done(row) if live else row["completed"]
        total = row["total"]
        return {"id": row["id"], "slug": slug, "state": row["state"], "total": total, "completed": completed,
                "percent": round(100 * completed / total, 1) if total else 100.0, "until": row["until_pct"], "until_budget": row["until_usd"],
                "target": target_of(total, row["until_pct"]), "spent": round(self._spent(row, slug), 6), "working": self.active(slug) if live else 0,
                "resumes": row["resumes"], "started_at": row["started_at"], "updated_at": row["updated_at"], "note": row["note"]}

    def status(self, slug: str) -> dict | None:
        row = self._latest(self.net._project(slug)["id"])
        return self._view(row, slug) if row else None

    # ---- starting ---------------------------------------------------------------------------------------------------------------------------------------

    def start(self, slug: str, spec: dict, until=None, until_budget=None, resume: bool = False) -> dict:
        """Start a run on `slug`, or with `resume` continue the latest unfinished one. `spec` is how to start the agents (kind, count, ...)."""
        with self._lock:
            project = self.net._project(slug)
            until = parse_until(until) if until is not None else None
            until_budget = parse_budget(until_budget) if until_budget is not None else None
            if self._live(slug):
                raise RunError(f"a run is already going on {slug}: `decomp run {slug} --stop` ends it")
            last = self._latest(project["id"])
            note = ""
            if resume and last and last["state"] in UNFINISHED:
                run_id = last["id"]
                use = {**json.loads(last["spec"]), **(spec or {})}
                until = until if until is not None else last["until_pct"]
                until_budget = until_budget if until_budget is not None else last["until_usd"]
                done = self._done(last)
                self._save(run_id, until_pct=until, until_usd=until_budget, completed=done, resumes=last["resumes"] + 1, spec=json.dumps(use), state="running",
                           note=f"resumed at {done} of {last['total']}")
                if last["total"] and done >= target_of(last["total"], until):
                    self._finish(run_id, slug, "complete", f"the target was already reached: {done} of {last['total']} matched, so nothing to start", halt=False)
                    return self.status(slug)
            else:
                if resume:
                    note = "no earlier run to resume: starting a new one. "
                if last and last["state"] in UNFINISHED:
                    self._save(last["id"], state="superseded")
                queue = [r["id"] for r in self.net.store.all("SELECT id FROM functions WHERE project_id=? AND status='open' ORDER BY id", project["id"])]
                use = dict(spec or {})
                with self.net.store.tx() as db:
                    cur = db.execute("INSERT INTO runs(project_id, started_at, updated_at, state, total, until_pct, until_usd, spend_at_start, queue, spec, note) "
                                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project["id"], self.clock(), self.clock(), "running", len(queue), until, until_budget,
                                                                        float((self.net.spend(slug) or {}).get("usd", 0)), json.dumps(queue), json.dumps(use), note))
                    run_id = cur.lastrowid
                if not queue:
                    self._finish(run_id, slug, "complete", note + "nothing to do: no function is open", halt=False)
                    return self.status(slug)
            try:
                ids = self.launch(slug, use)
                if not ids:
                    raise RunError("no agent could be started")
            except Exception as e:  # whatever stopped the agents from starting: say it on the run, then tell the person
                self._finish(run_id, slug, "ended", f"could not start the agents: {e}", halt=False)
                raise RunError(str(e)) from e
            self._spawn(slug, run_id)
            return self.status(slug)

    def _live(self, slug: str) -> bool:
        """Is a run going on this project? The database says, not a thread: after a stop the watching thread takes a moment to notice, and a resume must not be refused for that."""
        row = self._latest(self.net._project(slug)["id"])
        return bool(row) and row["state"] == "running"

    def _spawn(self, slug: str, run_id: int) -> None:
        stop = threading.Event()
        self._stops[slug] = stop
        thread = threading.Thread(target=self._loop, args=(slug, run_id, stop), daemon=True, name=f"run-{slug}")
        self._threads[slug] = thread
        thread.start()

    # ---- watching ---------------------------------------------------------------------------------------------------------------------------------------

    def _loop(self, slug: str, run_id: int, stop: threading.Event) -> None:
        while not stop.wait(self.poll):
            try:
                state = self.tick(slug)
            except Exception as e:  # a crash here must not leave agents spending with nobody watching: halt, record, stop
                log.warning("run on %s failed", slug, exc_info=True)
                row = self.net.store.one("SELECT * FROM runs WHERE id=?", run_id)
                if row and row["state"] == "running":
                    self._finish(run_id, slug, "interrupted", f"the run stopped on an error: {type(e).__name__}: {e}; `decomp run {slug} --resume` carries on")
                return
            if state is None or state["state"] != "running":
                return

    def tick(self, slug: str) -> dict | None:
        """Look at a run: count, save, and end it if its target or budget is reached or its agents have stopped. Returns its status."""
        with self._lock:
            row = self._latest(self.net._project(slug)["id"])
            if row is None or row["state"] != "running":
                return self._view(row, slug) if row else None
            done = self._done(row)
            spent = self._spent(row, slug)
            total, until = row["total"], row["until_pct"]
            if done >= target_of(total, until):
                what = f"reached {until}%" if until and until < 100 else "all done"
                self._finish(row["id"], slug, "complete", f"{what}: {done} of {total} functions matched")
            elif row["until_usd"] and spent >= row["until_usd"]:
                self._finish(row["id"], slug, "budget", f"the run's budget of ${row['until_usd']:g} was reached (${spent:.2f} spent); {done} of {total} matched. "
                                                        f"`decomp run {slug} --resume --until-budget <more>` carries on", done=done)
            elif self.active(slug) == 0:
                why = self.explain(slug)
                self._finish(row["id"], slug, "ended", f"the agents stopped on their own with {done} of {total} matched ({100 * done / total:.0f}%)"
                                                       + (f". Last error: {why}" if why else "") + f"; `decomp run {slug} --resume` carries on", halt=False, done=done)
            else:
                self._save(row["id"], completed=done)
            return self.status(slug)

    def _finish(self, run_id: int, slug: str, state: str, note: str, *, halt: bool = True, done: int | None = None) -> None:
        row = self.net.store.one("SELECT * FROM runs WHERE id=?", run_id)
        done = self._done(row) if done is None else done
        if halt:
            self.halt(slug)
        self._save(run_id, state=state, completed=done, note=note)
        stop = self._stops.get(slug)
        if stop is not None:
            stop.set()

    # ---- stopping, and after the app stops --------------------------------------------------------------------------------------------------------------

    def stop(self, slug: str) -> dict | None:
        """End the run now, gracefully: the agents are halted and what was done is saved. `--resume` carries on."""
        with self._lock:
            row = self._latest(self.net._project(slug)["id"])
            if row and row["state"] == "running":
                done = self._done(row)
                self._finish(row["id"], slug, "stopped", f"stopped at {done} of {row['total']}; `decomp run {slug} --resume` carries on", done=done)
            return self.status(slug)

    def recover(self) -> int:
        """At start-up: a run still marked running was cut off (the app died without flushing). Count where it got to and mark it interrupted."""
        n = 0
        for row in self.net.store.all("SELECT r.*, p.slug FROM runs r JOIN projects p ON p.id=r.project_id WHERE r.state='running'"):
            done = self._done(row)
            self._save(row["id"], state="interrupted", completed=done,
                       note=f"the app stopped at {done} of {row['total']}; `decomp run {row['slug']} --resume` carries on")
            n += 1
        return n

    def shutdown(self) -> None:
        """The app is stopping: flush every running run as interrupted, and end the watching threads."""
        with self._lock:
            for row in self.net.store.all("SELECT r.*, p.slug FROM runs r JOIN projects p ON p.id=r.project_id WHERE r.state='running'"):
                done = self._done(row)
                self._finish(row["id"], row["slug"], "interrupted", f"the app was stopped at {done} of {row['total']}; `decomp run {row['slug']} --resume` carries on", done=done)
        for thread in list(self._threads.values()):
            thread.join(timeout=5)
