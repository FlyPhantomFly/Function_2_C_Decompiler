"""`decomp backup` and `decomp restore`: your project work is one SQLite file, and it must be possible to keep a copy of it safely.

Why it is not `cp`: while the app runs the database is in WAL mode, so committed work can still be in the `-wal` file and a plain file copy
misses it (shown below, not assumed). SQLite's online backup API takes a consistent snapshot even while the app is writing. Restore is the
dangerous half: it must refuse while the app is running, keep the database it replaces, never modify the backup file it reads, and delete
stale `-wal` and `-shm` files so old pages cannot be replayed onto the restored database. The API keys are in settings.json, not the
database, so a backup can be shared without leaking them.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from decompnet.app import backup, cli
from decompnet.store import SCHEMA_VERSION, Store

FIXTURE = Path(__file__).parent / "fixtures" / "db-0.10.6.sqlite"  # a real database written by upstream 0.10.6: 13 functions, 1 matched


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path, table: str = "functions") -> list[tuple]:
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        return con.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    finally:
        con.close()


@pytest.fixture
def live(tmp_path):
    """A working database in a home folder, as the app leaves it when it is not running."""
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    db = home / ".decomp" / "decomp.db"
    shutil.copy(FIXTURE, db)
    return home, db


# ---- the snapshot ---------------------------------------------------------------------------------------------------------------------------------


def test_a_snapshot_holds_every_row_passes_the_integrity_check_and_says_what_it_holds(live, tmp_path):
    home, db = live
    info = backup.snapshot(db, tmp_path / "out" / "b.sqlite")
    assert rows(tmp_path / "out" / "b.sqlite") == rows(db) and rows(tmp_path / "out" / "b.sqlite", "notes") == rows(db, "notes")
    assert (info["projects"], info["functions"], info["matched"]) == (1, 13, 1) and info["bytes"] > 0 and info["path"] == tmp_path / "out" / "b.sqlite"
    check = sqlite3.connect(f"file:{tmp_path / 'out' / 'b.sqlite'}?mode=ro&immutable=1", uri=True)
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_taking_a_snapshot_changes_nothing_in_the_live_database_and_leaves_no_wal_files_behind(live, tmp_path):
    _, db = live
    before = rows(db)
    backup.snapshot(db, tmp_path / "b.sqlite")
    assert rows(db) == before
    assert sorted(p.name for p in db.parent.iterdir()) == ["decomp.db"]


def test_work_still_in_the_wal_is_in_the_snapshot_and_a_plain_file_copy_misses_it(live, tmp_path):
    """The reason this is not `cp`. The app holds the database open in WAL mode; a committed note can live only in the -wal file."""
    _, db = live
    store = Store(db)  # opens it as the app does: WAL mode
    store.conn.execute("INSERT INTO notes(project_id, text, created_at) VALUES (1, 'committed but not yet in the main file', 0)")
    assert db.with_name("decomp.db-wal").exists() and db.with_name("decomp.db-wal").stat().st_size > 0
    shutil.copy(db, tmp_path / "naive.sqlite")  # what copying the file gives you
    backup.snapshot(db, tmp_path / "proper.sqlite")
    texts = lambda p: [r[4] for r in rows(p, "notes")]  # noqa: E731
    assert "committed but not yet in the main file" in texts(tmp_path / "proper.sqlite")
    assert "committed but not yet in the main file" not in texts(tmp_path / "naive.sqlite")  # the data loss a file copy would have caused
    store.conn.close()


def test_a_snapshot_taken_while_the_app_is_writing_is_consistent(live, tmp_path):
    _, db = live
    store = Store(db)
    stop, written = threading.Event(), []

    def writer():
        i = 0
        while not stop.is_set():
            store.conn.execute("INSERT INTO notes(project_id, text, created_at) VALUES (1, ?, 0)", (f"note {i}",))
            written.append(i)
            i += 1

    thread = threading.Thread(target=writer)
    thread.start()
    time.sleep(0.2)
    info = backup.snapshot(db, tmp_path / "busy.sqlite")
    stop.set()
    thread.join()
    store.conn.close()
    got = [r[4] for r in rows(tmp_path / "busy.sqlite", "notes") if r[4].startswith("note ")]
    assert got == [f"note {i}" for i in range(len(got))]  # a prefix of what was written: no gaps, no torn rows
    assert 0 < len(got) <= len(written) and info["functions"] == 13


# ---- where it goes --------------------------------------------------------------------------------------------------------------------------------


def test_the_default_destination_is_a_timestamped_file_in_a_backups_folder_of_the_home(tmp_path):
    when = datetime.datetime(2026, 10, 22, 15, 30, 5)
    assert backup.default_destination(tmp_path, when) == tmp_path / "backups" / "decomp-backup-20261022-153005.sqlite"


def test_a_directory_as_destination_gets_a_timestamped_name_inside_it(live, tmp_path):
    _, db = live
    folder = tmp_path / "usb"
    folder.mkdir()
    info = backup.snapshot(db, folder)
    assert info["path"].parent == folder and info["path"].name.startswith("decomp-backup-") and info["path"].suffix == ".sqlite"


def test_an_existing_file_is_never_overwritten_unless_asked(live, tmp_path):
    _, db = live
    dest = tmp_path / "b.sqlite"
    dest.write_bytes(b"precious")
    with pytest.raises(backup.BackupError, match="already exists"):
        backup.snapshot(db, dest)
    assert dest.read_bytes() == b"precious"
    backup.snapshot(db, dest, force=True)
    assert rows(dest) == rows(db)


def test_backing_up_onto_the_live_database_is_refused(live):
    _, db = live
    before = sha(db)
    with pytest.raises(backup.BackupError, match="the live database"):
        backup.snapshot(db, db, force=True)
    assert sha(db) == before


def test_there_is_a_clear_message_when_nothing_has_been_imported_yet(tmp_path):
    with pytest.raises(backup.BackupError, match="nothing to back up"):
        backup.snapshot(tmp_path / "missing.db", tmp_path / "b.sqlite")


def test_a_failed_snapshot_leaves_no_file_that_looks_complete(live, tmp_path, monkeypatch):
    _, db = live

    def dying(source, destination):
        destination.write_bytes(b"half")
        raise OSError("disk full")

    monkeypatch.setattr(backup, "_copy", dying)
    with pytest.raises(OSError, match="disk full"):
        backup.snapshot(db, tmp_path / "out" / "b.sqlite")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == []


# ---- what counts as a backup ------------------------------------------------------------------------------------------------------------------


def test_a_file_that_is_not_one_of_ours_is_refused_with_a_reason(tmp_path):
    junk = tmp_path / "junk"
    junk.write_bytes(b"this is not a database at all, just some text " * 40)
    with pytest.raises(backup.BackupError, match="not a SQLite database"):
        backup.verify(junk)
    other = tmp_path / "other.sqlite"
    sqlite3.connect(other).executescript("CREATE TABLE unrelated(x); INSERT INTO unrelated VALUES (1);")
    with pytest.raises(backup.BackupError, match="not a Function_2_C_Decompiler database"):
        backup.verify(other)


def test_a_damaged_copy_is_refused(tmp_path):
    damaged = tmp_path / "damaged.sqlite"
    data = bytearray(FIXTURE.read_bytes())
    for i in range(len(data) // 3, len(data) // 3 + 4096):
        data[i] = 0xFF
    damaged.write_bytes(bytes(data))
    with pytest.raises(backup.BackupError, match="damaged"):
        backup.verify(damaged)


def test_a_backup_from_a_newer_version_is_refused(tmp_path):
    future = tmp_path / "future.sqlite"
    shutil.copy(FIXTURE, future)
    con = sqlite3.connect(future)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    con.close()
    with pytest.raises(backup.BackupError, match="newer"):
        backup.verify(future)


# ---- restore ---------------------------------------------------------------------------------------------------------------------------------------


def make_backup(db, tmp_path, name="b.sqlite"):
    return backup.snapshot(db, tmp_path / name)["path"]


def test_restore_replaces_the_database_keeps_the_old_one_and_never_touches_the_backup(live, tmp_path):
    _, db = live
    saved = make_backup(db, tmp_path)
    saved_hash = sha(saved)
    store = Store(db)
    store.conn.execute("DELETE FROM functions WHERE name='clamp_s32'")  # work lost since the backup
    store.conn.close()
    kept = backup.restore(saved, db, running=False, now=datetime.datetime(2026, 10, 22, 16, 0, 0))
    assert [r[2] for r in rows(db) if r[2] == "clamp_s32"] == ["clamp_s32"]  # back
    assert kept.name == "decomp.db.before-restore-20261022-160000" and not any(r[2] == "clamp_s32" for r in rows(kept))  # what was replaced is kept
    assert sha(saved) == saved_hash  # the user's backup file was only read


def test_restore_refuses_while_the_app_is_running_and_changes_nothing(live, tmp_path):
    _, db = live
    saved = make_backup(db, tmp_path)
    before = sha(db)
    with pytest.raises(backup.BackupError, match="stop it first"):
        backup.restore(saved, db, running=True)
    assert sha(db) == before and sorted(p.name for p in db.parent.iterdir()) == ["decomp.db"]


def test_restore_leaves_no_wal_or_shm_beside_the_restored_database_whatever_was_there_before(live, tmp_path):
    _, db = live
    saved = make_backup(db, tmp_path)
    wal, shm = db.with_name("decomp.db-wal"), db.with_name("decomp.db-shm")
    wal.write_bytes(b"stale frames from the database being replaced")
    shm.write_bytes(b"stale index")
    backup.restore(saved, db, running=False)
    assert not wal.exists() and not shm.exists()
    Store(db).conn.close()  # opens cleanly


def test_orphaned_wal_and_shm_files_with_no_database_beside_them_are_deleted_by_a_restore(tmp_path):
    """The case only the explicit deletion handles: when a database is present, snapshotting it (to keep it) makes SQLite tidy its own
    sidecar files, which hid this from the test above. Here there is no database, only leftovers that must not be adopted by the new one."""
    db = tmp_path / "h" / ".decomp" / "decomp.db"
    db.parent.mkdir(parents=True)
    wal, shm = db.with_name("decomp.db-wal"), db.with_name("decomp.db-shm")
    wal.write_bytes(b"orphaned frames")
    shm.write_bytes(b"orphaned index")
    assert backup.restore(FIXTURE, db, running=False) is None
    assert not wal.exists() and not shm.exists() and len(rows(db)) == 13


def test_restore_refuses_a_backup_from_a_newer_version_or_a_bad_file_and_the_current_database_is_untouched(live, tmp_path):
    _, db = live
    future = tmp_path / "future.sqlite"
    shutil.copy(FIXTURE, future)
    con = sqlite3.connect(future)
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    con.close()
    junk = tmp_path / "junk"
    junk.write_bytes(b"not a database " * 100)
    before = sha(db)
    for bad, why in ((future, "newer"), (junk, "not a SQLite database")):
        with pytest.raises(backup.BackupError, match=why):
            backup.restore(bad, db, running=False)
    assert sha(db) == before and sorted(p.name for p in db.parent.iterdir()) == ["decomp.db"]  # no half-done restore, no .restoring file


def test_restore_works_when_there_is_no_database_yet_as_on_a_new_computer(tmp_path):
    db = tmp_path / "newhome" / ".decomp" / "decomp.db"
    assert backup.restore(FIXTURE, db, running=False) is None
    assert len(rows(db)) == 13


def test_a_round_trip_through_a_backup_and_then_the_app_works_on_the_restored_database(live, tmp_path):
    _, db = live
    saved = make_backup(db, tmp_path)
    store = Store(db)
    store.conn.execute("UPDATE functions SET status='open', matched_source=NULL WHERE name='clamp_s32'")
    store.conn.close()
    backup.restore(saved, db, running=False)
    from decompnet.network import Network

    net = Network(db)
    assert net.store.one("SELECT status FROM functions WHERE name='clamp_s32'")["status"] == "matched"


# ---- the command line -------------------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def home(live, monkeypatch):
    h, _ = live
    monkeypatch.setenv("DECOMP_HOME", str(h))
    monkeypatch.setattr(cli, "_alive", lambda port: False)
    return h


def test_the_backup_command_writes_a_snapshot_into_the_homes_backups_folder_and_says_what_it_did(home, capsys):
    assert cli.main(["backup"]) == 0
    out = capsys.readouterr().out
    made = list((home / "backups").glob("decomp-backup-*.sqlite"))
    assert len(made) == 1 and "Backed up 1 project, 13 functions (1 matched)" in out and str(made[0]) in out
    assert "API keys" in out and "settings" in out  # it says what it does not hold


def test_the_backup_command_takes_a_destination(home, tmp_path, capsys):
    assert cli.main(["backup", str(tmp_path / "mine.sqlite")]) == 0
    assert (tmp_path / "mine.sqlite").exists() and not (home / "backups").exists()


def test_the_backup_command_reports_a_problem_as_one_error_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DECOMP_HOME", str(tmp_path / "empty"))
    assert cli.main(["backup"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "nothing to back up" in err and "Traceback" not in err


def test_restore_without_yes_says_what_it_would_do_and_does_nothing(home, tmp_path, capsys):
    saved = backup.snapshot(home / ".decomp" / "decomp.db", tmp_path / "b.sqlite")["path"]
    before = sha(home / ".decomp" / "decomp.db")
    assert cli.main(["restore", str(saved)]) == 1
    out = capsys.readouterr().out
    assert "--yes" in out and "replaces" in out and sha(home / ".decomp" / "decomp.db") == before


def test_restore_with_yes_does_it_and_reports_where_the_old_database_went(home, tmp_path, capsys):
    db = home / ".decomp" / "decomp.db"
    saved = backup.snapshot(db, tmp_path / "b.sqlite")["path"]
    assert cli.main(["restore", str(saved), "--yes"]) == 0
    out = capsys.readouterr().out
    assert "Restored 1 project, 13 functions (1 matched)" in out and "before-restore" in out
    assert len(list(db.parent.glob("decomp.db.before-restore-*"))) == 1


def test_restore_refuses_while_the_app_is_running(home, tmp_path, monkeypatch, capsys):
    db = home / ".decomp" / "decomp.db"
    saved = backup.snapshot(db, tmp_path / "b.sqlite")["path"]
    (home / ".decomp" / "server.json").write_text(json.dumps({"port": 6480, "secret": "s", "pid": 1}), encoding="utf-8")
    monkeypatch.setattr(cli, "_alive", lambda port: True)
    before = sha(db)
    assert cli.main(["restore", str(saved), "--yes"]) == 1
    assert "stop it first" in capsys.readouterr().err and sha(db) == before


def test_restore_of_a_file_that_is_not_there_is_one_error_line(home, capsys):
    assert cli.main(["restore", "/nonexistent/backup.sqlite", "--yes"]) == 1
    assert capsys.readouterr().err.startswith("error: ")
