"""Automatic rolling backups of the project database.

What it does: once a day it takes a verified snapshot (the same `backup.snapshot` that `decomp backup` uses, safe while the app writes) into `<home>/backups/auto/`, writes a
`sha256sum`-format checksum beside it, and prunes the folder to the retention you chose: **3 daily, 2 weekly, 1 monthly**. Once a week (and right after the first backup) it
restores the newest backup into a scratch folder and checks that what comes out is what went in: the checksum, SQLite's integrity check, and the project, function and match
counts recorded when the backup was made. A backup that cannot be restored is worse than none because it is trusted; this is what finds out.

The retention rule, exactly: keep the newest backup of each of the 3 most recent days that have one; of each of the 2 most recent ISO weeks before this week that have one; and
of the most recent calendar month before this month that has one. A backup can fill more than one of those places. So at most six are kept, however long the app has run; with few
backups, all of them are kept; and the newest is never deleted.

What it will not do: fill the disk (it needs about twice the database's size free, and says when it skips), touch anything in its folder it did not name (only
`decomp-auto-YYYYMMDD-HHMMSS.sqlite` and its `.sha256`), or touch your manual backups (`decomp backup` writes elsewhere and is never pruned). The copy `store.py` keeps before a
migration (`decomp.db.bak-v<N>`) is separate and is not pruned either; it has a checksum too.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

from .. import checksum
from . import backup

log = logging.getLogger("decomp.wtf")

KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 3, 2, 1
POLICY = f"{KEEP_DAILY} daily, {KEEP_WEEKLY} weekly, {KEEP_MONTHLY} monthly"
INTERVAL = dt.timedelta(hours=24)  # a backup is due when the newest is this old
TEST_EVERY = dt.timedelta(days=7)
SPACE_FACTOR = 2  # free space needed, in databases: the snapshot, and room to restore it for the test
NAME = re.compile(r"^decomp-auto-(\d{8})-(\d{6})\.sqlite$")

checksum_ok = checksum.check


def enabled_by_environment() -> bool:
    """`DECOMP_NO_AUTO_BACKUP` switches the whole thing off (tests, CI, a machine where you do not want a daemon writing to disk)."""
    return not os.environ.get("DECOMP_NO_AUTO_BACKUP")


def parse(name: str) -> dt.datetime | None:
    """When a backup file was made, from its name; None for anything that is not one of ours (so nothing else is ever touched)."""
    m = NAME.match(name)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def plan_retention(stamps: dict[str, dt.datetime], now: dt.datetime, daily: int = KEEP_DAILY, weekly: int = KEEP_WEEKLY, monthly: int = KEEP_MONTHLY) -> set[str]:
    """The names to KEEP (everything else may be deleted). See the module docstring for the rule."""
    def newest(group: list[str]) -> str:
        return max(group, key=lambda n: stamps[n])

    by_day: dict[dt.date, list[str]] = {}
    by_week: dict[tuple[int, int], list[str]] = {}
    by_month: dict[tuple[int, int], list[str]] = {}
    for n, t in stamps.items():
        by_day.setdefault(t.date(), []).append(n)
        by_week.setdefault(t.isocalendar()[:2], []).append(n)
        by_month.setdefault((t.year, t.month), []).append(n)
    keep = {newest(by_day[d]) for d in sorted(by_day, reverse=True)[:daily]}
    keep |= {newest(by_week[w]) for w in sorted((w for w in by_week if w < now.isocalendar()[:2]), reverse=True)[:weekly]}
    keep |= {newest(by_month[m]) for m in sorted((m for m in by_month if m < (now.year, now.month)), reverse=True)[:monthly]}
    return keep


def status_lines(status: dict, setting_on: bool = True) -> list[str]:
    """What `decomp backup --status` prints, from `AutoBackup.status()`."""
    if not enabled_by_environment():
        state = "off (DECOMP_NO_AUTO_BACKUP is set)"
    else:
        state = "on" if setting_on else "off (switched off in Settings)"
    n = status["count"]
    lines = [f"Automatic backups: {state}. Keeps {status['policy']}.", f"  {n} backup{'s' if n != 1 else ''}, {status['bytes'] / 1e6:.1f} MB, in {status['folder']}"]
    last = status.get("last")
    if last:
        what = (f" ({last['projects']} project{'s' if last['projects'] != 1 else ''}, {last['functions']:,} functions, {last['matched']:,} matched)" if "functions" in last else "")
        lines.append(f"  last backup: {last['at']}{what}")
    test = status.get("last_test")
    lines.append(f"  restore test: {'ok' if test['ok'] else 'FAILED'}, {test['at']}: {test['detail']}" if test else "  restore test: not run yet")
    if status.get("skipped"):
        lines.append(f"  skipped: {status['skipped']}")
    if status.get("error"):
        lines.append(f"  last error: {status['error']}")
    return lines


class AutoBackup:
    def __init__(self, home: Path, db: Path, *, enabled=lambda: True, clock=dt.datetime.now, first_delay: float = 45.0, check_every: float = 3600.0):
        self.home, self.db = Path(home), Path(db)
        self.folder = self.home / "backups" / "auto"
        self._enabled, self.clock = enabled, clock
        self.first_delay, self.check_every = first_delay, check_every
        self._skipped: str | None = None  # why the last attempt did nothing, and the last crash: kept in memory, shown in the app
        self._error: str | None = None
        self._stop, self._thread = threading.Event(), None
        self._lock = threading.Lock()

    # ---- what is on disk -----------------------------------------------------------------------------------------------------------------------------

    def _stamps(self) -> dict[str, dt.datetime]:
        if not self.folder.exists():
            return {}
        return {p.name: t for p in self.folder.iterdir() if (t := parse(p.name)) is not None}

    def _meta(self) -> dict:
        try:
            data = json.loads((self.folder / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data.setdefault("backups", {})
        return data

    def _save(self, meta: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / "status.json.part"
        tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        tmp.replace(self.folder / "status.json")

    # ---- deciding --------------------------------------------------------------------------------------------------------------------------------------

    def due(self, now: dt.datetime | None = None) -> bool:
        stamps = self._stamps()
        return not stamps or (now or self.clock()) - max(stamps.values()) >= INTERVAL

    def test_due(self, now: dt.datetime | None = None) -> bool:
        if not self._stamps():
            return False
        last = self._meta().get("last_test")
        return not last or (now or self.clock()) - dt.datetime.fromisoformat(last["at"]) >= TEST_EVERY

    # ---- doing -----------------------------------------------------------------------------------------------------------------------------------------

    def backup_now(self, now: dt.datetime | None = None) -> dict:
        """Take a snapshot now (whether or not one is due), checksum it, record it, prune. Returns what it holds, or {"skipped": why}."""
        with self._lock:
            now = now or self.clock()
            if not self.db.exists():
                return {"skipped": "nothing to back up yet"}
            need = SPACE_FACTOR * sum(p.stat().st_size for p in (self.db, self.db.with_name(self.db.name + "-wal")) if p.exists())
            free = shutil.disk_usage(self.home if not self.folder.exists() else self.folder).free
            if free < need:
                self._skipped = f"not enough free disk space (needs about {need // 2**20} MB free, has {free // 2**20} MB)"
                return {"skipped": self._skipped}
            dest = self.folder / f"decomp-auto-{now:%Y%m%d-%H%M%S}.sqlite"
            if dest.exists():
                return {"skipped": "a backup with this timestamp already exists"}
            info = backup.snapshot(self.db, dest)
            digest = checksum.write(dest)
            meta = self._meta()
            meta["backups"][dest.name] = {"at": now.isoformat(timespec="seconds"), "bytes": info["bytes"], "sha256": digest,
                                          "projects": info["projects"], "functions": info["functions"], "matched": info["matched"]}
            self._prune(meta, now)
            self._save(meta)
            self._skipped = self._error = None
            return {**info, "sha256": digest, "at": now.isoformat(timespec="seconds")}

    def _prune(self, meta: dict, now: dt.datetime) -> None:
        stamps = self._stamps()
        keep = plan_retention(stamps, now)
        for name in sorted(set(stamps) - keep):  # only files the app named; the sidecar goes with its backup
            for victim in (self.folder / name, checksum.sidecar(self.folder / name)):
                victim.unlink(missing_ok=True)
        meta["backups"] = {n: m for n, m in meta["backups"].items() if n in keep}

    def restore_test(self, now: dt.datetime | None = None) -> dict:
        """Restore the newest backup into a scratch folder and compare with what it held when it was made. Records the result; a failure is
        shown in the app and logged, and the backup that failed is kept as evidence."""
        with self._lock:
            now = now or self.clock()
            stamps = self._stamps()
            if not stamps:
                return {"ok": None, "detail": "no backup to test yet"}
            newest = max(stamps, key=stamps.get)
            path = self.folder / newest
            ok, detail = self._try_restore(path, self._meta()["backups"].get(newest))
            result = {"at": now.isoformat(timespec="seconds"), "file": newest, "ok": ok, "detail": detail}
            meta = self._meta()
            meta["last_test"] = result
            self._save(meta)
            if not ok:
                log.warning("automatic backup %s failed its restore test: %s", newest, detail)
            return result

    def _try_restore(self, path: Path, recorded: dict | None) -> tuple[bool, str]:
        same = checksum.check(path)
        if same is None:
            return False, "there is no checksum file to check it against"
        if not same:
            return False, "the checksum does not match: the file changed after it was made"
        scratch = Path(tempfile.mkdtemp(prefix="restore-test-", dir=self.home / "backups"))
        try:
            backup.verify(path)
            target = scratch / "decomp.db"
            backup.restore(path, target, running=False)
            got = backup.describe(target)
        except backup.BackupError as e:
            return False, f"it cannot be restored: {e}"
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        counts = (got["projects"], got["functions"], got["matched"])
        text = f"restored {got['projects']} project{'s' if got['projects'] != 1 else ''}, {got['functions']:,} functions ({got['matched']:,} matched)"
        if recorded is None:
            return True, f"{text}; there is no record of what it held to compare with"
        expected = (recorded["projects"], recorded["functions"], recorded["matched"])
        if counts != expected:
            return False, f"{text}, but it was recorded as holding {expected[1]:,} functions ({expected[0]} projects, {expected[2]:,} matched)"
        return True, f"{text}, as recorded; integrity ok"

    def run_once(self, now: dt.datetime | None = None) -> dict:
        """What the scheduler does each time it wakes: a backup if one is due, a restore test if one is due."""
        if not self._enabled():
            return {"disabled": True}
        now = now or self.clock()
        done: dict = {}
        if self.due(now):
            done["backup"] = self.backup_now(now)
        if self.test_due(now):
            done["test"] = self.restore_test(now)
        return done

    # ---- showing ---------------------------------------------------------------------------------------------------------------------------------------

    def status(self) -> dict:
        stamps = self._stamps()
        meta = self._meta()
        newest = max(stamps, key=stamps.get) if stamps else None
        last = ({"file": newest, **meta["backups"][newest]} if newest and newest in meta["backups"] else
                ({"file": newest, "at": stamps[newest].isoformat(timespec="seconds")} if newest else None))
        size = sum(p.stat().st_size for p in self.folder.iterdir() if p.is_file()) if self.folder.exists() else 0
        return {"enabled": bool(self._enabled()), "policy": POLICY, "folder": str(self.folder), "count": len(stamps), "bytes": size, "last": last,
                "last_test": meta.get("last_test"), "skipped": self._skipped, "error": self._error,
                "next_due": (stamps[newest] + INTERVAL).isoformat(timespec="seconds") if newest else None}

    # ---- the thread ------------------------------------------------------------------------------------------------------------------------------------

    def start(self) -> None:
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="auto-backup")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        if self._stop.wait(self.first_delay):  # not while the app is still starting
            return
        while True:
            try:
                self.run_once()
            except Exception as e:  # a failing backup must never take the app down: it is recorded, shown and logged, and the loop goes on
                self._error = f"{type(e).__name__}: {e}"
                log.warning("automatic backup failed", exc_info=True)
            if self._stop.wait(self.check_every):
                return
