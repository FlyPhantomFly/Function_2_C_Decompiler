"""The automatic backups, through the running app: the status in the state, the Back up now route, the setting, and the thread stopping with the app."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from decompnet.app import autobackup, backup
from decompnet.app.engine import RomNetwork
from decompnet.app.server import build

PORT, SECRET = 6497, "s3cret-for-autobackup-tests"
H = {"X-Decomp": "1"}
STATIC = Path(__file__).resolve().parents[2] / "src" / "decompnet" / "app" / "static"


@pytest.fixture
def app(tmp_path):
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    mcp, manager, security = build(net, home / ".decomp", PORT, SECRET)
    client = TestClient(mcp.streamable_http_app(transport_security=security, host="127.0.0.1"), base_url=f"http://127.0.0.1:{PORT}")
    client.cookies.set("decomp_live", SECRET)
    yield client, home, manager
    manager.on_stop()


def threads() -> int:
    return sum(1 for t in threading.enumerate() if t.name == "auto-backup" and t.is_alive())


def test_the_state_carries_the_backup_status_and_the_tests_run_with_the_thread_switched_off_by_the_environment(app):
    client, home, _ = app
    b = client.get("/api/state").json()["backups"]
    assert b["policy"] == "3 daily, 2 weekly, 1 monthly" and b["count"] == 0 and b["last"] is None and b["folder"] == str(home / "backups" / "auto")
    assert b["enabled"] is False  # the conftest sets DECOMP_NO_AUTO_BACKUP: no thread works inside a test's home
    assert client.get("/api/state").json()["settings"]["auto_backup"] is True  # the setting itself is on by default


def test_back_up_now_needs_the_header_makes_a_verified_backup_and_returns_the_new_status(app):
    client, home, _ = app
    assert client.post("/api/backup", json={}).status_code == 403  # a cross-site form cannot send the header
    r = client.post("/api/backup", json={}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["skipped"] is None and body["backups"]["count"] == 1
    made = sorted((home / "backups" / "auto").glob("decomp-auto-*.sqlite"))
    assert len(made) == 1 and autobackup.checksum_ok(made[0]) is True
    backup.verify(made[0])


def test_the_setting_round_trips_and_is_what_the_scheduler_obeys(app, monkeypatch):
    client, _, _ = app
    monkeypatch.delenv("DECOMP_NO_AUTO_BACKUP")  # as on a real machine
    assert client.get("/api/state").json()["backups"]["enabled"] is True
    assert client.post("/api/settings", json={"auto_backup": False}, headers=H).json()["auto_backup"] is False
    assert client.get("/api/state").json()["backups"]["enabled"] is False
    assert client.post("/api/settings", json={"auto_backup": True}, headers=H).json()["auto_backup"] is True
    assert client.get("/api/state").json()["backups"]["enabled"] is True


def test_back_up_now_works_even_when_the_automatic_ones_are_switched_off(app):
    client, _, _ = app
    client.post("/api/settings", json={"auto_backup": False}, headers=H)
    assert client.post("/api/backup", json={}, headers=H).json()["backups"]["count"] == 1


def test_a_failing_backup_is_one_clear_error_not_a_traceback(app, monkeypatch):
    client, _, _ = app

    def refuse(db, dest, **kw):
        raise backup.BackupError("the disk said no")

    monkeypatch.setattr(backup, "snapshot", refuse)
    r = client.post("/api/backup", json={}, headers=H)
    assert r.status_code == 400 and "the disk said no" in r.text and "Traceback" not in r.text


def test_stopping_the_app_stops_the_backup_thread(tmp_path):
    before = threads()
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    _, manager, _ = build(net, home / ".decomp", PORT + 1, SECRET)
    assert threads() == before + 1  # started with the app, asleep until its first check
    manager.on_stop()
    assert threads() == before


def test_the_settings_screen_has_the_toggle_the_status_line_and_the_button_and_a_failed_restore_test_is_shown_in_the_open():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for needle in ('id="autoBackupSet"', 'id="backupNow"', 'id="backupText"', "/api/backup", "function backupLine", "auto_backup", "Restore test FAILED", "3 daily, 2 weekly and 1 monthly"):
        assert needle in js, needle
