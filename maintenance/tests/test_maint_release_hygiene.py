"""Release hygiene for this fork: one version everywhere, and a changelog entry for every version.

These are the mechanical half of the working agreement ("a version bump for every change, with a changelog tracking
the updates"): a change that bumps the version in one place only, or bumps without writing it down, fails here.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from decompnet import __version__

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "maintenance" / "CHANGELOG.md"
HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2}|upstream)$", re.M)  # `upstream`: the anchor entry


def _load_bump():
    spec = importlib.util.spec_from_file_location("bump_version", ROOT / "maintenance" / "tools" / "bump_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump_version = _load_bump()


def test_the_version_is_the_same_in_pyproject_init_and_the_lock():
    versions = bump_version.read_versions()
    assert set(versions.values()) == {__version__}, versions


def test_the_changelog_leads_with_the_current_version():
    releases = HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))
    assert releases, "maintenance/CHANGELOG.md has no '## [X.Y.Z] - YYYY-MM-DD' entries"
    assert releases[0][0] == __version__, f"newest changelog entry is {releases[0][0]} but the code is {__version__}"


def test_every_changelog_entry_is_unique_and_newest_first():
    versions = [bump_version.key(v) for v, _ in HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))]
    assert versions == sorted(set(versions), reverse=True)


def test_the_changelog_starts_from_the_upstream_release_we_forked():
    versions = [v for v, _ in HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))]
    assert versions[-1] == "0.10.6"  # upstream's last release; every later entry is ours


# ---- the bump tool itself, against a throwaway copy of the three files --------------------------------------------

PYPROJECT = '[project]\nname = "decompnet"\nversion = "0.10.6"\nrequires-python = ">=3.12"\n'
INIT = '"""DecompNet."""\n\n__version__ = "0.10.6"\n'
LOCK = ('version = 1\n\n[[package]]\nname = "capstone"\nversion = "5.0.9"\n\n'
        '[[package]]\nname = "decompnet"\nversion = "0.10.6"\nsource = { editable = "." }\n')


@pytest.fixture
def fake(tmp_path, monkeypatch):
    files = {"pyproject.toml": (tmp_path / "pyproject.toml", PYPROJECT), "src/decompnet/__init__.py": (tmp_path / "init.py", INIT),
             "uv.lock": (tmp_path / "uv.lock", LOCK)}
    places = {}
    for name, (path, text) in files.items():
        path.write_text(text, encoding="utf-8")
        places[name] = (path, bump_version.PLACES[name][1])
    monkeypatch.setattr(bump_version, "PLACES", places)
    # the tool shells out to `uv lock --check`; the stub says it passed, without touching the real subprocess module
    monkeypatch.setattr(bump_version, "subprocess", SimpleNamespace(run=lambda *a, **k: SimpleNamespace(returncode=0)))
    return places


def test_bump_rewrites_all_three_places_and_only_the_projects_own_lock_entry(fake):
    bump_version.bump("0.10.7")
    assert set(bump_version.read_versions().values()) == {"0.10.7"}
    lock = fake["uv.lock"][0].read_text(encoding="utf-8")
    assert 'name = "capstone"\nversion = "5.0.9"' in lock  # another package's version is left alone


def test_bump_refuses_when_the_places_already_disagree(fake):
    fake["src/decompnet/__init__.py"][0].write_text(INIT.replace("0.10.6", "0.10.5"), encoding="utf-8")
    with pytest.raises(SystemExit, match="disagree"):
        bump_version.bump("0.10.7")
    assert 'version = "0.10.6"' in fake["pyproject.toml"][0].read_text(encoding="utf-8")  # nothing half-written


@pytest.mark.parametrize("bad", ["0.10.6", "0.10.5", "0.9.99", "1.0", "0.10.7-fork.1", "v0.10.7", ""])
def test_bump_refuses_versions_that_are_not_a_plain_newer_x_y_z(fake, bad):
    with pytest.raises(SystemExit):
        bump_version.bump(bad)
    assert set(bump_version.read_versions().values()) == {"0.10.6"}
