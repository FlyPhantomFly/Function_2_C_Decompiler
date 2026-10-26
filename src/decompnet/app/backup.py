"""Back up and restore the project database: the work (matches, attempts, notes, names) of every imported game.

`decomp backup` takes a consistent snapshot with SQLite's online backup API, so it is safe while the app runs. A plain file copy is not: the
database is in WAL mode, and committed work can still sit in the `-wal` file, which a copy of `decomp.db` alone misses. The snapshot is written
under a temporary name, checked (it is a SQLite file, passes `integrity_check`, has our tables, and is a format this version understands), and
only then renamed into place, so a failed run never leaves something that looks like a good backup.

`decomp restore` is the dangerous half and is careful: it refuses while the app is running (replacing a database under a live connection
corrupts it), works on a COPY of the backup so the file you gave it is only ever read, verifies that copy before touching anything, keeps the
database it replaces (never overwriting an earlier kept one), and deletes the old database's `-wal` and `-shm` files so their pages cannot be
replayed onto the restored file.

What it holds, and does not: the project database only. API keys and settings are in `settings.json`, not here, so a backup can be shared
without leaking them. Game files and forked projects' git repositories are yours and already live elsewhere.
"""

from __future__ import annotations

import datetime
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from .. import checksum
from ..store import SCHEMA_VERSION


class BackupError(RuntimeError):
    """Something to tell the user in a sentence: nothing to back up, a bad file, the app still running."""


def default_destination(home: Path, now: datetime.datetime | None = None) -> Path:
    return home / "backups" / f"decomp-backup-{_stamp(now)}.sqlite"


def _stamp(now: datetime.datetime | None) -> str:
    return (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")


def _read_only(path: Path) -> sqlite3.Connection:
    """A look at a FILE nobody else is writing (a backup or a staged copy): immutable, so SQLite creates no -wal or -shm beside it."""
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro&immutable=1", uri=True)


def _copy(source: sqlite3.Connection, destination: Path) -> None:
    with closing(sqlite3.connect(str(destination))) as out:
        source.backup(out)  # a consistent snapshot, including what is only in the WAL, even while the app is writing


def _snapshot_of(db: Path, destination: Path) -> None:
    source = sqlite3.connect(str(db))
    try:
        source.execute("PRAGMA query_only = ON")  # this connection reads; it cannot change the live database
        _copy(source, destination)
    finally:
        source.close()


def verify(path: Path) -> int:
    """Raise BackupError unless `path` is a sound database of ours that this version can open. Returns its format version."""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError as e:
        raise BackupError(f"cannot read {path}: {e.strerror or e}") from e
    if head != b"SQLite format 3\x00":
        raise BackupError(f"{path} is not a SQLite database")
    try:
        with closing(_read_only(path)) as con:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError(f"{path} is damaged (SQLite's integrity check failed)")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            version = con.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.DatabaseError as e:
        raise BackupError(f"{path} is damaged ({e})") from e
    if not {"functions", "projects"} <= tables:
        raise BackupError(f"{path} is not a Function_2_C_Decompiler database")
    if version > SCHEMA_VERSION:
        raise BackupError(f"{path} was written by a newer Function_2_C_Decompiler (its database format is version {version}, and this one "
                          f"understands up to {SCHEMA_VERSION}). Update first.")
    return version


def check_sidecar(path: Path) -> None:
    """Refuse a backup whose `.sha256` beside it says the file has changed since it was written. No sidecar (a manual backup) is fine."""
    if checksum.check(Path(path)) is False:
        raise BackupError(f"{path} does not match its checksum ({checksum.sidecar(path).name}): the file changed after it was made, or the checksum file is wrong. Not using it.")


def describe(path: Path) -> dict:
    """What a database holds, for the one-line summary."""
    with closing(_read_only(path)) as con:
        def count(sql: str) -> int:
            try:
                return int(con.execute(sql).fetchone()[0])
            except sqlite3.DatabaseError:
                return 0

        return {"projects": count("SELECT COUNT(*) FROM projects"), "functions": count("SELECT COUNT(*) FROM functions"),
                "matched": count("SELECT COUNT(*) FROM functions WHERE status='matched'"), "bytes": Path(path).stat().st_size}


def snapshot(db: Path, dest: Path, *, force: bool = False) -> dict:
    """Write a verified snapshot of `db` to `dest` (a file, or a folder to put a timestamped file in). Returns what it holds and where it is."""
    db, dest = Path(db), Path(dest)
    if not db.exists():
        raise BackupError("there is nothing to back up yet: no game has been imported")
    if dest.is_dir() or str(dest).endswith(("/", os.sep)):
        dest = dest / default_destination(Path()).name
    if dest.resolve() == db.resolve():
        raise BackupError("that is the live database: choose another destination")
    if dest.exists() and not force:
        raise BackupError(f"{dest} already exists (add --force to replace it)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        _snapshot_of(db, part)
        verify(part)
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)  # never leave something that looks like a backup and is not
        raise
    return describe(dest) | {"path": dest}


def _kept_name(db: Path, now: datetime.datetime | None) -> Path:
    """Where the database being replaced goes: never over an earlier one (two restores in a second get -2, -3...)."""
    base = db.with_name(f"{db.name}.before-restore-{_stamp(now)}")
    candidate, n = base, 2
    while candidate.exists():
        candidate, n = base.with_name(f"{base.name}-{n}"), n + 1
    return candidate


def restore(backup_file: Path, db: Path, *, running: bool, now: datetime.datetime | None = None) -> Path | None:
    """Replace `db` with the verified contents of `backup_file`. Returns where the replaced database was kept (None if there was none)."""
    if running:
        raise BackupError("Function_2_C_Decompiler is running: stop it first (decomp stop). Replacing its database underneath it would corrupt it.")
    backup_file, db = Path(backup_file), Path(db)
    check_sidecar(backup_file)
    db.parent.mkdir(parents=True, exist_ok=True)
    staged = db.with_name(db.name + ".restoring")
    kept: Path | None = None
    kept_part: Path | None = None
    try:
        try:
            shutil.copyfile(backup_file, staged)  # a copy: the backup file itself is only ever read
        except OSError as e:
            raise BackupError(f"cannot read {backup_file}: {e.strerror or e}") from e
        verify(staged)
        if db.exists():
            kept = _kept_name(db, now)
            kept_part = kept.with_name(kept.name + ".part")
            _snapshot_of(db, kept_part)  # what is being replaced, whole, WAL included, before anything is destroyed
            kept_part.replace(kept)
        for suffix in ("-wal", "-shm"):  # the old database's: replayed onto the restored file they would corrupt it
            db.with_name(db.name + suffix).unlink(missing_ok=True)
        os.replace(staged, db)
    except BaseException:
        staged.unlink(missing_ok=True)
        if kept_part is not None:
            kept_part.unlink(missing_ok=True)
        raise
    return kept
