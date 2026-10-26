"""`decomp toolchain list | install | path`: the one way to install a specific pinned compiler from the command line.

It used to be `decompnet toolchain ...`, a subcommand of the hosted-network CLI. That CLI is going away with the rest of the
hosted service, and the app CLI (`decomp`) only had `setup`, which installs the free default set. These tests pin the
behavior that was ported (and the safety property that matters: a proprietary compiler is never installed without
`--accept-license`), and fail if anything in the repository still tells a user to run the old command.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decompnet import toolchains
from decompnet.app import cli

ROOT = Path(__file__).resolve().parents[2]
OLD = "decompnet " + "toolchain"  # spelled in two pieces so this file does not trip its own scan


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))  # toolchains.root() lives under it
    return tmp_path


def test_list_shows_every_toolchain_and_where_they_install(capsys):
    assert cli.main(["toolchain", "list"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split()[:3] == ["id", "platform", "license"]
    for tid in toolchains.registry():
        assert tid in out
    assert f"install dir: {toolchains.root()}" in out


def test_list_says_which_toolchains_are_installed(capsys):
    where = toolchains.path("m2c")
    where.mkdir(parents=True)
    (where / toolchains.MANIFEST).write_text(json.dumps({"id": "m2c"}), encoding="utf-8")
    assert cli.main(["toolchain", "list"]) == 0
    lines = {line.split()[0]: line for line in capsys.readouterr().out.splitlines() if line.strip()}
    assert "installed" in lines["m2c"] and "installed" not in lines["gcc-2.7.2-kmc"]


def test_an_unknown_toolchain_is_a_clean_error_not_a_traceback(capsys):
    assert cli.main(["toolchain", "install", "no-such-thing"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: unknown toolchain 'no-such-thing'") and "Traceback" not in err


@pytest.mark.parametrize("tid", [t for t, tc in toolchains.registry().items() if tc.proprietary])
def test_a_proprietary_compiler_is_never_installed_without_the_license_flag(tid, monkeypatch, capsys):
    def forbidden(*a, **k):
        raise AssertionError("something was downloaded before the license was accepted")

    monkeypatch.setattr(toolchains, "_download", forbidden)
    assert cli.main(["toolchain", "install", tid]) == 1
    err = capsys.readouterr().err
    assert "proprietary" in err and "--accept-license" in err


def test_the_flags_reach_install_and_default_to_off(monkeypatch):
    seen = []
    monkeypatch.setattr(toolchains, "install", lambda tid, **kw: seen.append((tid, kw)))
    assert cli.main(["toolchain", "install", "m2c"]) == 0
    assert cli.main(["toolchain", "install", "ido-7.1", "--accept-license", "--force"]) == 0
    assert seen == [("m2c", {"accept_license": False, "force": False}), ("ido-7.1", {"accept_license": True, "force": True})]


def test_path_prints_the_install_directory(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(toolchains, "require", lambda tid: tmp_path / tid)
    assert cli.main(["toolchain", "path", "m2c"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "m2c")


def test_path_of_a_missing_toolchain_names_the_command_that_installs_it(capsys):
    assert cli.main(["toolchain", "path", "m2c"]) == 1
    assert "run `decomp toolchain install m2c`" in capsys.readouterr().err


def test_a_toolchain_subcommand_is_required(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["toolchain"])
    assert stop.value.code == 2


def test_nothing_in_the_repository_tells_anyone_to_run_the_old_command():
    skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".ruff_cache", "patches", "raw"}
    skip_files = {"CHANGELOG.md", "uv.lock", Path(__file__).name}  # the changelog records history; the lock is generated
    hits = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or skip_dirs & set(path.relative_to(ROOT).parts) or path.name in skip_files:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{path.relative_to(ROOT)}:{n}" for n, line in enumerate(text.splitlines(), 1) if OLD in line]
    assert hits == [], hits
