"""Makes `db-0.10.6.sqlite`: a real database written by UPSTREAM decomp.wtf 0.10.6, for the schema-migration tests.

Run it with the untouched upstream tree (git tag `upstream-0.10.6`, its own environment), never with this fork's code:

    git worktree add /tmp/upstream upstream-0.10.6 && cd /tmp/upstream && uv sync --locked
    uv run python /path/to/maintenance/tests/fixtures/make_db_0_10_6.py projects/demo  /path/to/db-0.10.6.sqlite

It only uses methods that exist in 0.10.6, and drives them the way the app does: import the demo project, register an agent,
make a wrong attempt, then a matching one, leave a note, release a claim, and edit the shared header. The demo project is
this repository's own sample game; the only token in the file is a hash of a random one.
"""

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import decompnet

assert decompnet.__version__ == "0.10.6", f"this must run on upstream 0.10.6, not {decompnet.__version__}"

sys.path.insert(0, str(Path.cwd()))  # the upstream checkout, for tests/solutions.py
from decompnet.network import Network  # noqa: E402
from decompnet.project import import_project  # noqa: E402
from tests.solutions import SOLUTIONS, WRONG_CLAMP  # noqa: E402

demo, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory() as tmp:
    work = Path(tmp) / "demo"
    shutil.copytree(demo, work, ignore=shutil.ignore_patterns("target"))
    (work / "target").mkdir()
    net = Network(Path(tmp) / "work.db")
    import_project(net.store, work, log=lambda *_: None)
    agent = net.authenticate(net.register_agent("fixture-agent", "maintenance"))
    net.claim(agent, function="clamp_s32")
    net.compile_and_diff(agent, "clamp_s32", WRONG_CLAMP)  # an attempt with a score
    assert "MATCH" in net.compile_and_diff(agent, "clamp_s32", SOLUTIONS["clamp_s32"])  # and a match
    net.claim(agent, function="abs_s32")
    net.add_note(agent, None, "a note written by upstream 0.10.6", function="abs_s32")
    net.release(agent, "abs_s32", "left open on purpose")
    net.edit_context(agent, "demo", "", "s32 fixture_proto(s32 x);", "add a prototype")  # a second context version
    net.store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    out.unlink(missing_ok=True)
    net.store.conn.execute(f"VACUUM INTO '{out}'")  # one clean file, no -wal or -shm beside it
    net.store.conn.close()
print("wrote", out, out.stat().st_size, "bytes; user_version =", sqlite3.connect(out).execute("PRAGMA user_version").fetchone()[0])
