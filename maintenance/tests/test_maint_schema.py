"""The database is the user's work: it must survive an upgrade, and must not be misread by a version that does not understand it.

Upstream never versioned its schema (`PRAGMA user_version` is 0 in every database it wrote) and migrated by adding columns in
place. That works, but it cannot tell a database from the future from one it knows, and the first migration of an old database
runs UPDATE and DELETE statements on real work with no copy kept. These tests pin the replacement: a version stamp; a real
upstream 0.10.6 database (made by upstream's own code, see fixtures/README.md) opens, migrates and keeps every row; the first
migration leaves the untouched original beside it; a newer database is refused without being touched; and each of the eleven
column migrations works on a table that already holds data.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from decompnet import store
from decompnet.store import MIGRATIONS, SCHEMA_VERSION, Store, StoreError

FIXTURE = Path(__file__).parent / "fixtures" / "db-0.10.6.sqlite"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version_of(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def dump(path: Path, columns_of: dict[str, list[str]] | None = None) -> dict[str, list[tuple]]:
    """Every row of every table (only `columns_of`'s columns when given), in a stable order."""
    con = sqlite3.connect(path)
    try:
        out = {}
        for (table,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
            if columns_of is not None and table not in columns_of:
                continue  # a table a migration added: not part of "what the original had", which is what is being compared
            cols = columns_of[table] if columns_of else [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            out[table] = con.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY rowid").fetchall()
        return out
    finally:
        con.close()


def columns(path: Path) -> dict[str, list[str]]:
    con = sqlite3.connect(path)
    try:
        return {t: [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
                for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()}
    finally:
        con.close()


@pytest.fixture
def upstream_db(tmp_path):
    path = tmp_path / "decomp.db"
    shutil.copy(FIXTURE, path)
    return path


# ---- the fixture is what it claims to be -----------------------------------------------------------------------------


def test_the_fixture_is_an_unversioned_upstream_database_with_real_work_in_it():
    assert version_of(FIXTURE) == 0
    rows = {t: len(r) for t, r in dump(FIXTURE).items()}
    assert rows["functions"] == 13 and rows["agents"] == 1 and rows["attempts"] == 2 and rows["context_versions"] == 2
    assert rows["notes"] >= 1 and rows["events"] >= 1
    con = sqlite3.connect(FIXTURE)
    assert con.execute("SELECT name, status FROM functions WHERE status='matched'").fetchall() == [("clamp_s32", "matched")]


# ---- the version stamp ------------------------------------------------------------------------------------------------


def test_a_new_database_is_stamped_with_the_current_version_and_makes_no_backup(tmp_path):
    path = tmp_path / "new.db"
    Store(path).conn.close()
    assert version_of(path) == SCHEMA_VERSION >= 1
    assert sorted(p.name for p in tmp_path.iterdir() if ".bak" in p.name) == []


def test_an_upstream_database_opens_migrates_and_keeps_every_row(upstream_db):
    before_cols = columns(upstream_db)
    before = dump(upstream_db)
    store_ = Store(upstream_db)
    store_.conn.close()
    assert version_of(upstream_db) == SCHEMA_VERSION
    after = dump(upstream_db, before_cols)  # the columns upstream had: nothing in them may change
    for table, rows in before.items():
        assert after[table] == rows, table
    assert {t: len(r) for t, r in after.items()} == {t: len(r) for t, r in before.items()}


def test_the_first_migration_keeps_a_complete_restorable_copy_of_the_original_beside_it(upstream_db, tmp_path):
    original = dump(upstream_db)
    Store(upstream_db).conn.close()
    backup = upstream_db.with_name(upstream_db.name + ".bak-v0")
    assert backup.exists() and version_of(backup) == 0
    assert dump(backup) == original  # every row and column, as upstream wrote them (not byte for byte: SQLite's backup rewrites pages)
    check = sqlite3.connect(backup)
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    check.close()
    restored = tmp_path / "restored.db"  # restoring is renaming the copy back: it must open, and migrate again
    shutil.copy(backup, restored)
    Store(restored).conn.close()
    assert version_of(restored) == SCHEMA_VERSION and dump(restored, columns(backup)) == original


def test_opening_again_changes_no_data_and_makes_no_second_backup(upstream_db):
    Store(upstream_db).conn.close()
    first = dump(upstream_db)
    backups = sorted(p.name for p in upstream_db.parent.iterdir() if ".bak" in p.name)
    Store(upstream_db).conn.close()
    assert dump(upstream_db) == first
    assert sorted(p.name for p in upstream_db.parent.iterdir() if ".bak" in p.name) == backups == ["decomp.db.bak-v0", "decomp.db.bak-v0.sha256"]  # the copy and, since 0.10.49, its checksum


def test_an_existing_backup_is_never_overwritten(upstream_db):
    backup = upstream_db.with_name(upstream_db.name + ".bak-v0")
    backup.write_bytes(b"an earlier backup the user made or kept")
    Store(upstream_db).conn.close()
    assert backup.read_bytes() == b"an earlier backup the user made or kept"


def test_a_failed_backup_stops_the_migration_and_leaves_nothing_that_looks_complete(upstream_db, monkeypatch):
    def dying_copy(source, destination):
        destination.write_bytes(b"half a database")  # what a copy that dies midway leaves behind
        raise OSError("disk full")

    monkeypatch.setattr(store, "_copy_database", dying_copy)
    before = sha(upstream_db)
    with pytest.raises(OSError, match="disk full"):
        Store(upstream_db)
    assert sha(upstream_db) == before and version_of(upstream_db) == 0  # not migrated, not even switched to WAL
    assert sorted(p.name for p in upstream_db.parent.iterdir()) == ["decomp.db"]  # no complete-looking backup, no .part left


def test_an_upstream_database_still_works_through_the_real_network_class(upstream_db):
    """Not just rows: an agent can register against it and claim, and what upstream had matched is still matched."""
    from decompnet.network import Network

    net = Network(upstream_db)
    agent = net.authenticate(net.register_agent("someone-new", "tests"))
    text = net.claim(agent, function="abs_s32")
    assert text.startswith("## CLAIMED: demo/abs_s32") and "Target assembly" in text
    row = net.store.one("SELECT status, matched_source, attempts FROM functions WHERE name='clamp_s32'")
    assert row["status"] == "matched" and "s32 clamp_s32" in row["matched_source"] and row["attempts"] == 2
    assert {r["name"] for r in net.store.all("SELECT name FROM agents")} == {"fixture-agent", "someone-new"}


# ---- a database from the future ----------------------------------------------------------------------------------------


def test_a_database_from_a_newer_version_is_refused_and_not_touched(tmp_path):
    path = tmp_path / "future.db"
    shutil.copy(FIXTURE, path)
    con = sqlite3.connect(path)
    con.execute("PRAGMA user_version = 99")
    con.close()
    before = sha(path)
    with pytest.raises(StoreError) as refused:
        Store(path)
    message = str(refused.value)
    assert "newer" in message and "99" in message and str(SCHEMA_VERSION) in message
    assert sha(path) == before  # not even switched to WAL
    assert sorted(p.name for p in tmp_path.iterdir()) == ["future.db"]  # no backup, no -wal, no -shm


def test_a_database_exactly_at_the_current_version_opens_without_a_backup(tmp_path):
    path = tmp_path / "current.db"
    Store(path).conn.close()
    Store(path).conn.close()
    assert sorted(p.name for p in tmp_path.iterdir() if ".bak" in p.name) == []


# ---- each migration, on a table that already has rows ---------------------------------------------------------------------


@pytest.mark.parametrize("table, column, ddl", MIGRATIONS)
def test_every_column_migration_works_on_a_database_that_lacks_the_column(tmp_path, table, column, ddl):
    path = tmp_path / "old.db"
    Store(path).conn.close()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO agents(name, token_hash) VALUES ('a', 'h')")
    con.execute("INSERT INTO projects(slug, root, config) VALUES ('p', '/x', '{}')")
    con.execute("INSERT INTO functions(project_id, name) VALUES (1, 'f')")
    con.execute("INSERT INTO context_versions(project_id, version, header) VALUES (1, 1, '')")
    con.execute("INSERT INTO attempts(function_id, agent_id, score) VALUES (1, 1, 5)")
    for index in ("idx_functions_unit", "idx_functions_progress", "idx_functions_status", "idx_attempts_agent_time"):
        con.execute(f"DROP INDEX IF EXISTS {index}")  # SQLite will not drop an indexed column
    con.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    con.execute("PRAGMA user_version = 0")
    con.commit()
    con.close()
    assert column not in columns(path)[table]
    Store(path).conn.close()
    assert column in columns(path)[table]
    assert version_of(path) == SCHEMA_VERSION
    con = sqlite3.connect(path)
    assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1  # the row survived
    if "NOT NULL" in ddl:
        assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL").fetchone()[0] == 0  # and got its default
    con.close()


def test_the_one_time_recount_of_abandons_runs_once_and_is_not_repeated(tmp_path):
    path = tmp_path / "old.db"
    Store(path).conn.close()
    con = sqlite3.connect(path)
    con.execute("INSERT INTO projects(slug, root, config) VALUES ('p', '/x', '{}')")
    con.execute("INSERT INTO functions(project_id, name, abandons) VALUES (1, 'f', 5)")
    con.execute("DELETE FROM settings WHERE key = 'abandons_recounted'")
    con.commit()
    con.close()
    Store(path).conn.close()  # an old database: the recount runs, and finds no releases in the events
    con = sqlite3.connect(path)
    assert con.execute("SELECT abandons FROM functions").fetchone()[0] == 0
    assert con.execute("SELECT value FROM settings WHERE key='abandons_recounted'").fetchone()[0] == "1"
    con.execute("UPDATE functions SET abandons = 7")
    con.commit()
    con.close()
    Store(path).conn.close()
    assert sqlite3.connect(path).execute("SELECT abandons FROM functions").fetchone()[0] == 7  # not recounted again


def test_a_database_that_was_a_partial_migration_finishes_it(tmp_path):
    """A crash between two ALTERs leaves version 0 and some columns missing; the next open completes it."""
    path = tmp_path / "half.db"
    Store(path).conn.close()
    con = sqlite3.connect(path)
    for index in ("idx_functions_unit", "idx_functions_progress", "idx_functions_status"):
        con.execute(f"DROP INDEX IF EXISTS {index}")
    con.execute("ALTER TABLE functions DROP COLUMN boost")
    con.execute("PRAGMA user_version = 0")
    con.commit()
    con.close()
    Store(path).conn.close()
    assert "boost" in columns(path)["functions"] and version_of(path) == SCHEMA_VERSION


# ---- through the app --------------------------------------------------------------------------------------------------------


def test_the_app_says_one_clear_line_and_stops_for_a_database_from_a_newer_version(tmp_path, monkeypatch, capsys):
    from decompnet.app import cli

    monkeypatch.setenv("DECOMP_HOME", str(tmp_path))
    db = tmp_path / ".decomp" / "decomp.db"
    db.parent.mkdir()
    shutil.copy(FIXTURE, db)
    con = sqlite3.connect(db)
    con.execute("PRAGMA user_version = 42")
    con.close()
    assert cli.run(SimpleNamespace(port=0, no_browser=True)) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "newer Function_2_C_Decompiler" in err and "Traceback" not in err
    assert version_of(db) == 42  # untouched
