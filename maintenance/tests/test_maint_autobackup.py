"""Automatic rolling backups: daily, with the retention you chose (3 daily, 2 weekly, 1 monthly), a checksum for each, and a restore test now and then.

The point of an automatic backup is that you do not have to remember it, so the dangerous failures are quiet ones: a backup that is never made, one that cannot be restored,
one that fills the disk, one deleted by a clever retention rule that was wrong at a year boundary. Each has a test. The retention rule is a pure function, so it is checked against
explicit histories, including the turn of an ISO year (2027-01-03 is a Sunday that still belongs to week 53 of 2026).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from decompnet.app import autobackup, backup, cli
from decompnet.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "db-0.10.6.sqlite"  # 1 project, 13 functions, 1 matched


def name(stamp: dt.datetime) -> str:
    return f"decomp-auto-{stamp:%Y%m%d-%H%M%S}.sqlite"


def history(start: dt.date, end: dt.date, at=dt.time(3, 0)) -> dict[str, dt.datetime]:
    out, day = {}, start
    while day <= end:
        stamp = dt.datetime.combine(day, at)
        out[name(stamp)] = stamp
        day += dt.timedelta(days=1)
    return out


def days(kept: set[str]) -> list[str]:
    return sorted(f"{n[12:16]}-{n[16:18]}-{n[18:20]}" for n in kept)


# ---- the retention rule ------------------------------------------------------------------------------------------------------------------------------


def test_the_rule_keeps_the_newest_of_each_of_the_last_3_days_2_weeks_before_this_one_and_the_last_month():
    now = dt.datetime(2026, 10, 22, 9, 0)  # a Thursday, ISO week 43
    kept = autobackup.plan_retention(history(dt.date(2026, 8, 24), dt.date(2026, 10, 22)), now)
    assert days(kept) == ["2026-09-30", "2026-10-11", "2026-10-18", "2026-10-20", "2026-10-21", "2026-10-22"]


def test_the_rule_is_right_at_the_turn_of_an_iso_year():
    now = dt.datetime(2027, 1, 5, 9, 0)  # ISO week 1 of 2027; Jan 3 is still week 53 of 2026
    kept = autobackup.plan_retention(history(dt.date(2026, 11, 20), dt.date(2027, 1, 5)), now)
    assert days(kept) == ["2026-12-27", "2026-12-31", "2027-01-03", "2027-01-04", "2027-01-05"]


def test_several_backups_in_one_day_count_once_and_the_newest_wins():
    stamps = {name(dt.datetime(2026, 10, 22, h)): dt.datetime(2026, 10, 22, h) for h in (1, 9, 23)}
    kept = autobackup.plan_retention(stamps, dt.datetime(2026, 10, 22, 23, 30))
    assert kept == {name(dt.datetime(2026, 10, 22, 23))}


def test_with_few_backups_everything_is_kept_however_old_so_a_rarely_used_app_never_loses_its_only_copies():
    stamps = {name(s): s for s in (dt.datetime(2026, 1, 5, 3), dt.datetime(2026, 9, 1, 3), dt.datetime(2026, 10, 21, 3))}
    assert autobackup.plan_retention(stamps, dt.datetime(2026, 10, 22, 9)) == set(stamps)


def test_nothing_gives_nothing_and_the_newest_backup_is_never_among_the_deleted():
    assert autobackup.plan_retention({}, dt.datetime(2026, 10, 22)) == set()
    for gap in (0, 1, 2, 3, 10, 45, 400):
        stamps = history(dt.date(2025, 1, 1), dt.date(2026, 10, 22) - dt.timedelta(days=gap))
        newest = max(stamps, key=stamps.get)
        assert newest in autobackup.plan_retention(stamps, dt.datetime(2026, 10, 22, 9))


def test_it_never_keeps_more_than_six_however_long_the_history():
    assert len(autobackup.plan_retention(history(dt.date(2024, 1, 1), dt.date(2026, 10, 22)), dt.datetime(2026, 10, 22, 9))) == 6


def test_only_names_the_app_made_are_ever_parsed():
    assert autobackup.parse("decomp-auto-20261022-030000.sqlite") == dt.datetime(2026, 10, 22, 3, 0, 0)
    for other in ("decomp-backup-20261022-030000.sqlite", "decomp-auto-20261022-030000.sqlite.sha256", "my-notes.txt", "decomp-auto-2026-10-22.sqlite", "decomp-auto-20261322-030000.sqlite"):
        assert autobackup.parse(other) is None


# ---- making one -----------------------------------------------------------------------------------------------------------------------------------------

NOW = dt.datetime(2026, 10, 22, 3, 0, 0)


@pytest.fixture
def box(tmp_path):
    """A home with a real (upstream 0.10.6) database, and a scheduler with a clock we move."""
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    db = home / ".decomp" / "decomp.db"
    shutil.copy(FIXTURE, db)
    clock = {"now": NOW}
    scheduler = autobackup.AutoBackup(home, db, clock=lambda: clock["now"])
    return SimpleBox(home, db, clock, scheduler)


class SimpleBox:
    def __init__(self, home, db, clock, scheduler):
        self.home, self.db, self.clock, self.scheduler = home, db, clock, scheduler

    @property
    def folder(self) -> Path:
        return self.home / "backups" / "auto"

    def files(self) -> list[str]:
        return sorted(p.name for p in self.folder.iterdir()) if self.folder.exists() else []


def test_a_backup_is_a_verified_snapshot_with_a_checksum_in_the_format_sha256sum_reads(box):
    made = box.scheduler.backup_now()
    assert box.files() == [name(NOW), name(NOW) + ".sha256", "status.json"]  # the backup, its checksum, and the counts recorded for the restore test
    path = box.folder / name(NOW)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (box.folder / (name(NOW) + ".sha256")).read_text() == f"{digest}  {name(NOW)}\n"
    assert (made["projects"], made["functions"], made["matched"], made["sha256"]) == (1, 13, 1, digest)
    if shutil.which("sha256sum"):
        assert subprocess.run(["sha256sum", "--check", name(NOW) + ".sha256"], cwd=box.folder, capture_output=True).returncode == 0
    backup.verify(path)  # the same checks a manual backup passes


def test_the_checksum_catches_a_changed_file_a_missing_sidecar_and_a_sidecar_that_names_nothing(box):
    box.scheduler.backup_now()
    path = box.folder / name(NOW)
    assert autobackup.checksum_ok(path) is True
    side = box.folder / (name(NOW) + ".sha256")
    original = side.read_text()
    side.unlink()
    assert autobackup.checksum_ok(path) is None  # no checksum to check against: unknown, not "fine"
    side.write_text("not a checksum\n")
    assert autobackup.checksum_ok(path) is False
    side.write_text(original)
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    assert autobackup.checksum_ok(path) is False


def test_it_is_due_when_there_is_none_or_the_newest_is_a_day_old_and_not_before(box):
    s = box.scheduler
    assert s.due() is True and s.run_once()["backup"]["path"].name == name(NOW)
    assert s.due() is False and "backup" not in s.run_once()
    box.clock["now"] = NOW + dt.timedelta(hours=23, minutes=59)
    assert s.due() is False
    box.clock["now"] = NOW + dt.timedelta(hours=24)
    assert s.due() is True and "backup" in s.run_once()


def test_a_disabled_scheduler_does_nothing_at_all(box):
    off = autobackup.AutoBackup(box.home, box.db, enabled=lambda: False, clock=lambda: NOW)
    assert off.run_once() == {"disabled": True} and box.files() == [] and off.status()["enabled"] is False


def test_the_environment_variable_turns_it_off_even_when_the_setting_is_on(box, monkeypatch):
    assert autobackup.enabled_by_environment() is False  # the conftest sets it
    monkeypatch.delenv("DECOMP_NO_AUTO_BACKUP")
    assert autobackup.enabled_by_environment() is True


def test_nothing_is_made_when_there_is_no_database_yet_and_it_says_why(tmp_path):
    s = autobackup.AutoBackup(tmp_path, tmp_path / ".decomp" / "decomp.db", clock=lambda: NOW)
    assert s.run_once()["backup"] == {"skipped": "nothing to back up yet"} and not (tmp_path / "backups").exists()


def test_it_will_not_fill_the_disk_it_skips_and_says_so(box, monkeypatch):
    size = box.db.stat().st_size
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10 * size, 9 * size, size))  # only one database's worth free
    made = box.scheduler.run_once()["backup"]
    assert "not enough free disk space" in made["skipped"] and box.files() == []
    assert "not enough free disk space" in box.scheduler.status()["skipped"]
    monkeypatch.undo()
    assert "path" in box.scheduler.backup_now() and box.scheduler.status()["skipped"] is None  # a later success clears the warning


# ---- the rolling window in practice ---------------------------------------------------------------------------------------------------------------------


def test_run_every_day_for_two_months_the_folder_settles_to_six_backups_and_their_checksums_and_touches_nothing_else(box):
    box.folder.mkdir(parents=True)
    (box.folder / "my-notes.txt").write_text("not ours")
    (box.home / "backups" / "decomp-backup-20260101-000000.sqlite").write_bytes(b"a manual backup")
    for day in range(60):
        box.clock["now"] = NOW + dt.timedelta(days=day)
        box.scheduler.run_once()
    ours = [f for f in box.files() if f.endswith(".sqlite")]
    assert len(ours) == 6 and len([f for f in box.files() if f.endswith(".sha256")]) == 6  # no orphaned sidecars
    # the last day is Sunday 2026-12-20 (ISO week 51): the 3 newest days, the newest of the weeks of Dec 7 and Nov 30, and the newest of November.
    # Pruning day by day ends where the rule applied to the whole history does (checked independently of the code).
    assert days(set(ours)) == ["2026-11-30", "2026-12-06", "2026-12-13", "2026-12-18", "2026-12-19", "2026-12-20"]
    assert (box.folder / "my-notes.txt").read_text() == "not ours"
    assert (box.home / "backups" / "decomp-backup-20260101-000000.sqlite").read_bytes() == b"a manual backup"
    status = json.loads((box.folder / "status.json").read_text())
    assert sorted(status["backups"]) == sorted(ours)  # the metadata of deleted backups is gone too


def test_a_backup_made_while_the_app_writes_is_still_consistent(box):
    store = Store(box.db)
    store.conn.execute("INSERT INTO notes(project_id, text, created_at) VALUES (1, 'written just before the backup', 0)")
    box.scheduler.backup_now()
    store.conn.close()
    con = sqlite3.connect(f"{(box.folder / name(NOW)).resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    assert "written just before the backup" in [r[0] for r in con.execute("SELECT text FROM notes")]


# ---- the restore test -------------------------------------------------------------------------------------------------------------------------------------


def test_the_restore_test_really_restores_and_compares_with_what_the_backup_held(box):
    box.scheduler.backup_now()
    result = box.scheduler.restore_test()
    assert result["ok"] is True and "13 functions" in result["detail"] and result["file"] == name(NOW)
    assert box.scheduler.status()["last_test"]["ok"] is True
    assert box.files() == [name(NOW), name(NOW) + ".sha256", "status.json"]  # the test leaves no temporary restore behind


def test_the_restore_test_compares_with_the_backup_not_with_the_live_database_which_has_moved_on(box):
    box.scheduler.backup_now()
    store = Store(box.db)
    store.conn.execute("DELETE FROM functions WHERE name='clamp_s32'")
    store.conn.close()
    assert box.scheduler.restore_test()["ok"] is True


@pytest.mark.parametrize("damage, expected", [("flip", "checksum"), ("sidecar", "checksum"), ("truncate", "checksum")])
def test_a_damaged_backup_fails_the_test_loudly_and_is_not_deleted(box, damage, expected):
    box.scheduler.backup_now()
    path = box.folder / name(NOW)
    if damage == "flip":
        data = bytearray(path.read_bytes())
        data[len(data) // 3] ^= 0xFF
        path.write_bytes(bytes(data))
    elif damage == "sidecar":
        (box.folder / (name(NOW) + ".sha256")).write_text(f"{'0' * 64}  {name(NOW)}\n")
    else:
        path.write_bytes(path.read_bytes()[:4096])
    result = box.scheduler.restore_test()
    assert result["ok"] is False and expected in result["detail"]
    assert path.exists() and box.scheduler.status()["last_test"]["ok"] is False  # a failure is shown, and the evidence kept


def test_a_backup_whose_contents_do_not_match_what_was_recorded_fails_even_with_a_matching_checksum(box):
    box.scheduler.backup_now()
    meta = box.folder / "status.json"
    data = json.loads(meta.read_text())
    data["backups"][name(NOW)]["functions"] = 99
    meta.write_text(json.dumps(data))
    result = box.scheduler.restore_test()
    assert result["ok"] is False and "13 functions" in result["detail"] and "99" in result["detail"]


def test_with_no_backup_yet_there_is_nothing_to_test(box):
    assert box.scheduler.restore_test() == {"ok": None, "detail": "no backup to test yet"}


def test_the_test_runs_after_the_first_backup_and_then_weekly_not_daily(box):
    s = box.scheduler
    first = s.run_once()
    assert first["backup"] and first["test"]["ok"] is True  # early reassurance
    box.clock["now"] = NOW + dt.timedelta(days=1)
    assert "test" not in s.run_once()
    box.clock["now"] = NOW + dt.timedelta(days=6, hours=23)
    assert "test" not in s.run_once()
    box.clock["now"] = NOW + dt.timedelta(days=7)
    assert s.run_once()["test"]["ok"] is True


# ---- the thread ----------------------------------------------------------------------------------------------------------------------------------------------


def test_the_thread_makes_a_backup_stops_when_asked_and_a_crash_inside_is_recorded_not_raised(box, monkeypatch):
    s = autobackup.AutoBackup(box.home, box.db, first_delay=0.01, check_every=0.02)
    s.start()
    deadline = time.time() + 5
    while time.time() < deadline and not (box.folder.exists() and any(p.suffix == ".sqlite" for p in box.folder.iterdir())):
        time.sleep(0.02)
    s.stop()
    assert any(p.suffix == ".sqlite" for p in box.folder.iterdir()) and not s.running()
    crashing = autobackup.AutoBackup(box.home, box.db, first_delay=0.01, check_every=0.02, clock=lambda: dt.datetime.now() + dt.timedelta(days=3))  # relative to the real clock the first scheduler stamped its backup with
    monkeypatch.setattr(crashing, "backup_now", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk exploded")))
    crashing.start()
    deadline = time.time() + 5
    while time.time() < deadline and not crashing.status().get("error"):
        time.sleep(0.02)
    crashing.stop()
    assert "disk exploded" in crashing.status()["error"] and not crashing.running()


# ---- the one before a migration, and restoring any of them ------------------------------------------------------------------------------------------------------


def test_the_copy_kept_before_a_migration_has_a_checksum_too(tmp_path):
    path = tmp_path / "decomp.db"
    shutil.copy(FIXTURE, path)
    Store(path).conn.close()
    copy = tmp_path / "decomp.db.bak-v0"
    assert copy.exists() and autobackup.checksum_ok(copy) is True


def test_restoring_a_backup_refuses_when_its_checksum_says_it_changed_and_says_nothing_when_there_is_none(box, tmp_path, monkeypatch, capsys):
    box.scheduler.backup_now()
    monkeypatch.setenv("DECOMP_HOME", str(box.home))
    monkeypatch.setattr(cli, "_alive", lambda port: False)
    path = box.folder / name(NOW)
    before = box.db.read_bytes()
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    assert cli.main(["restore", str(path), "--yes"]) == 1
    assert "checksum" in capsys.readouterr().err and box.db.read_bytes() == before
    plain = tmp_path / "plain.sqlite"
    shutil.copy(FIXTURE, plain)  # no sidecar: a manual backup, restored as before
    assert cli.main(["restore", str(plain), "--yes"]) == 0


def test_the_status_command_prints_what_the_app_would_show(box, monkeypatch, capsys):
    box.scheduler.run_once()
    monkeypatch.setenv("DECOMP_HOME", str(box.home))
    assert cli.main(["backup", "--status"]) == 0
    out = capsys.readouterr().out
    assert "Automatic backups" in out and "1 backup" in out and "restore test: ok" in out and "3 daily, 2 weekly, 1 monthly" in out
