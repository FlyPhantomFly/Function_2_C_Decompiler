"""The updater must only ever read from, and install from, this fork.

Upstream's updater looked at `i12bp8/decomp.wtf` and `https://decomp.wtf`, and an `install.json` written by upstream's
installer pinned that repo even if the constant changed. Left alone, a copy of this fork would offer to replace
itself with someone else's code. Everything here runs offline: the network functions are stand-ins that record what
they were asked for.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from decompnet import __version__
from decompnet.app import updates

FORK = "FlyPhantomFly/Function_2_C_Decompiler"
UPSTREAM_MARKERS = ("i12bp8", "decomp.wtf")


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "data"


def _newer() -> str:
    major, minor, patch = updates.version_key(__version__)
    return f"{major}.{minor}.{patch + 1}"


def _record_gets(monkeypatch, body: str):
    asked: list[str] = []

    def get(url, timeout=15):
        asked.append(url)
        return body.encode()

    monkeypatch.setattr(updates, "_get", get)
    return asked


def test_the_updater_is_configured_for_this_fork_and_has_no_release_site():
    assert updates.REPO == FORK
    assert updates.SITE == ""
    assert updates.enabled() is True


def test_the_updaters_own_source_names_no_upstream_host_or_repo():
    source = Path(updates.__file__).read_text(encoding="utf-8")
    assert "i12bp8" not in source
    assert "https://decomp.wtf" not in source and "decomp.wtf/" not in source


def test_the_release_check_reads_only_this_forks_repository(monkeypatch):
    asked = _record_gets(monkeypatch, f'VERSION="{_newer()}"\n')
    found = updates.check()
    assert found["available"] and found["error"] is None
    assert asked == [f"https://raw.githubusercontent.com/{FORK}/main/site/public/install.sh"]
    assert found["spec"] == f"decompnet @ https://github.com/{FORK}/archive/refs/tags/v{_newer()}.tar.gz"


def test_a_repo_recorded_by_another_installer_is_ignored(monkeypatch):
    """install.json written by upstream's installer says channel=branch, repo=i12bp8/decomp.wtf."""
    updates.info_file().parent.mkdir(parents=True, exist_ok=True)
    updates.info_file().write_text(json.dumps({"channel": "branch", "repo": "i12bp8/decomp.wtf",
                                               "branch": "main", "commit": "a" * 40}), encoding="utf-8")
    assert updates.installed()["repo"] == FORK
    asked: list[str] = []

    def j(url):
        asked.append(url)
        return {"sha": "b" * 40, "commit": {"message": "x", "committer": {"date": "d"}}, "status": "ahead", "commits": []}

    monkeypatch.setattr(updates, "_json", j)
    monkeypatch.setattr(updates, "_branch_version", lambda repo, sha: "9.9.9")
    found = updates.check()
    assert asked and all(f"/repos/{FORK}/" in url for url in asked), asked
    assert FORK in found["spec"] and "i12bp8" not in found["spec"]


def test_recording_an_install_never_stores_another_repo():
    stored = updates.record("branch", "main", "c" * 40, repo="i12bp8/decomp.wtf")
    assert stored["repo"] == FORK
    assert json.loads(updates.info_file().read_text(encoding="utf-8"))["repo"] == FORK


def test_an_empty_repo_turns_updates_off_and_touches_no_network(monkeypatch):
    monkeypatch.setattr(updates, "REPO", "")

    def forbidden(*args, **kwargs):
        raise AssertionError("an update host was contacted while updates are off")

    for name in ("_get", "_json", "_branch_version"):
        monkeypatch.setattr(updates, name, forbidden)
    assert updates.enabled() is False
    found = updates.check()
    assert found["disabled"] is True and found["available"] is False and found["error"] is None
    assert found["can_apply"] is False and "off" in found["why_not"]
    assert updates.Updater(lambda: None, 1, "s").status()["disabled"] is True
    with pytest.raises(ValueError, match="off"):
        updates.Updater(lambda: None, 1, "s").apply()
    with pytest.raises(RuntimeError, match="off"):
        updates.install({"current": updates.installed(), "latest": {}, "spec": "decompnet @ https://x.test/a.tar.gz"})


def test_install_refuses_a_package_from_anywhere_but_this_fork(monkeypatch, tmp_path):
    ran: list = []
    monkeypatch.setattr(updates, "uv", lambda: "/nonexistent/uv")
    monkeypatch.setattr(updates, "_stream", lambda *a, **k: ran.append(a))
    for spec in ("decompnet @ https://github.com/i12bp8/decomp.wtf/archive/refs/tags/v9.0.0.tar.gz",
                 "decompnet @ https://decomp.wtf/dl/decompnet-9.0.0-py3-none-any.whl",
                 f"decompnet @ https://github.com/{FORK}.evil/archive/v9.tar.gz",
                 f"decompnet @ https://evil.test/https://github.com/{FORK}/archive/v9.tar.gz",
                 "decompnet"):
        found = {"current": updates.installed(), "latest": {"version": "9.0.0", "commit": ""}, "spec": spec}
        with pytest.raises(RuntimeError, match="isn't from"):
            updates.install(found)
    assert ran == []  # uv was never run for any of them


@pytest.mark.parametrize("hostile", ["1.0/../../evil", "1.0.0#x", "1.0.0 --index-url http://evil.test", "../1.0.0", "1.0.0?x=1", ""])
def test_a_hostile_version_string_from_the_network_is_rejected(monkeypatch, hostile):
    _record_gets(monkeypatch, f'VERSION="{hostile}"\n')
    found = updates.check()
    assert not found["available"] and found["error"], found


def test_a_release_site_is_used_when_one_is_configured_and_github_when_it_is_down(monkeypatch):
    monkeypatch.setattr(updates, "SITE", "https://updates.example.test")
    asked: list[str] = []

    def get(url, timeout=15):
        asked.append(url)
        return f'VERSION="{_newer()}"\n'.encode()

    monkeypatch.setattr(updates, "_get", get)
    assert updates.check()["spec"] == f"decompnet @ https://updates.example.test/dl/decompnet-{_newer()}-py3-none-any.whl"
    assert asked == ["https://updates.example.test/install.sh"]


def test_the_windows_message_does_not_send_anyone_to_upstreams_installer(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    ok, why = updates.can_apply()
    assert ok is False
    assert not any(marker in why for marker in UPSTREAM_MARKERS), why


def test_decomp_update_says_when_updates_are_off_instead_of_claiming_up_to_date(monkeypatch, tmp_path, capsys):
    from decompnet.app import cli

    monkeypatch.setenv("DECOMP_HOME", str(tmp_path))
    monkeypatch.setattr(updates, "REPO", "")
    assert cli.update_cmd(SimpleNamespace(check=False)) == 1
    out = capsys.readouterr().out
    assert "off" in out and "up to date" not in out


def test_the_gui_endpoint_stays_quiet_when_updates_are_off(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from decompnet.app.engine import RomNetwork
    from decompnet.app.server import build

    monkeypatch.setattr(updates, "REPO", "")
    monkeypatch.setenv("DECOMP_UPDATES", "on")  # the user hasn't switched checks off: the missing source is what does it

    def forbidden(*args, **kwargs):
        raise AssertionError("an update host was contacted while updates are off")

    for name in ("_get", "_json", "_branch_version"):
        monkeypatch.setattr(updates, name, forbidden)
    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    mcp, _manager, security = build(net, home / ".decomp", 6497, "sec")
    client = TestClient(mcp.streamable_http_app(transport_security=security, host="127.0.0.1"), base_url="http://127.0.0.1:6497")
    client.cookies.set("decomp_live", "sec")
    for query in ("", "?refresh=1"):
        body = client.get(f"/api/update{query}").json()
        assert body["disabled"] is True and body["available"] is False, body
    assert client.post("/api/update", json={"apply": True}, headers={"X-Decomp": "1"}).status_code == 400


def test_the_hostile_version_pattern_still_accepts_every_real_version_we_could_ship():
    """The validation must not reject our own releases: plain X.Y.Z, and the usual pre/post-release spellings."""
    for good in ("0.10.9", "0.11.0", "1.0.0", "0.11.0rc1", "0.11.0.post1", "0.11.0-fork.1"):
        assert re.fullmatch(updates.VERSION_OK, good), good


# ---- a branch update must never be a downgrade -----------------------------------------------------------------------
# Found by installing from a clone for real: the installer records channel=branch and the clone's commit. If that commit
# was never pushed (the maintainer has not pushed yet), GitHub answers 404 to the compare call and the old code offered
# the branch's newest commit, however old: here, an untouched upstream 0.10.6 that still has the upstream-pointing updater.


def _branch_world(monkeypatch, remote_version: str, *, known_commit: bool):
    have, head = "1" * 40, "2" * 40
    updates.record("branch", "main", have)

    def j(url):
        if "/compare/" in url:
            if known_commit:
                return {"status": "ahead", "commits": [{"commit": {"message": "newer work"}}]}
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return {"sha": head, "commit": {"message": "the branch's newest", "committer": {"date": "2026-10-21"}}}

    monkeypatch.setattr(updates, "_json", j)
    monkeypatch.setattr(updates, "_branch_version", lambda repo, sha: remote_version)


def test_an_unpushed_install_is_not_offered_the_branchs_older_code(monkeypatch):
    _branch_world(monkeypatch, "0.10.6", known_commit=False)  # upstream's version, still on the fork's main
    found = updates.check()
    assert found["available"] is False and found["latest"]["version"] == __version__


def test_a_newer_version_on_the_branch_is_still_offered_even_when_the_installed_commit_is_unknown(monkeypatch):
    _branch_world(monkeypatch, _newer(), known_commit=False)
    assert updates.check()["available"] is True


def test_new_commits_with_the_same_version_are_offered(monkeypatch):
    _branch_world(monkeypatch, __version__, known_commit=True)  # work between version bumps is a normal update
    assert updates.check()["available"] is True


def test_an_older_version_is_not_offered_even_when_the_commit_is_known(monkeypatch):
    _branch_world(monkeypatch, "0.10.6", known_commit=True)
    assert updates.check()["available"] is False


def test_a_branch_whose_version_cannot_be_read_is_not_offered(monkeypatch):
    _branch_world(monkeypatch, "", known_commit=False)  # raw.githubusercontent.com failed, or no version line
    assert updates.check()["available"] is False
