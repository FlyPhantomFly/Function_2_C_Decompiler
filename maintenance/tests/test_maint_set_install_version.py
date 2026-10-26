"""`set_install_version.py`: the one step that moves the installer's VERSION, and only to a release that exists.

Run in-process against a small temporary repository with a local bare repository standing in for GitHub, so "the tag exists on origin" is tested with a real `git ls-remote`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import set_install_version as tool  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "HOME": "/nonexistent", "PATH": "/usr/bin:/bin"}
SCRIPT = '#!/usr/bin/env bash\nset -euo pipefail\n\nVERSION="{v}"\nREPO="x/y"\necho hi\n'


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


def repo(tmp_path: Path, installer="0.11.0", package="0.12.0", entries=("0.12.0", "0.11.0"), tags=("v0.11.0",), origin=True) -> Path:
    root = tmp_path / "repo"
    (root / "site" / "public").mkdir(parents=True)
    (root / "maintenance").mkdir()
    (root / "site" / "public" / "install.sh").write_text(SCRIPT.format(v=installer), encoding="utf-8")
    (root / "pyproject.toml").write_text(f'[project]\nname = "decompnet"\nversion = "{package}"\n', encoding="utf-8")
    (root / "maintenance" / "CHANGELOG.md").write_text("# Changelog\n\n" + "".join(f"## [{v}] - 2026-01-01\n\nnotes\n\n" for v in entries), encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x")
    if origin:
        bare = tmp_path / "origin.git"
        git(tmp_path, "init", "-q", "--bare", str(bare))
        git(root, "remote", "add", "origin", str(bare))
        for tag in tags:
            git(root, "tag", tag)
        git(root, "push", "-q", "origin", "HEAD:refs/heads/main", "--tags")
    return root


def run(root: Path, *args: str) -> int:
    return tool.main([*args, "--root", str(root)])


def installer(root: Path) -> str:
    return (root / "site" / "public" / "install.sh").read_text(encoding="utf-8")


def test_it_moves_the_version_to_a_release_whose_tag_exists_and_changes_that_one_line_only(tmp_path, capsys):
    root = repo(tmp_path, tags=("v0.11.0", "v0.12.0"))
    before = installer(root).splitlines()
    assert run(root, "0.12.0") == 0
    after = installer(root).splitlines()
    assert [(a, b) for a, b in zip(before, after, strict=True) if a != b] == [('VERSION="0.11.0"', 'VERSION="0.12.0"')]
    assert "0.11.0 -> 0.12.0" in capsys.readouterr().out


def test_it_refuses_a_release_whose_tag_is_not_on_origin_yet_and_says_to_publish_first(tmp_path, capsys):
    root = repo(tmp_path)  # only v0.11.0 is published
    before = installer(root)
    assert run(root, "0.12.0") == 1
    assert "does not exist on origin yet" in capsys.readouterr().err and installer(root) == before


def test_it_refuses_when_it_cannot_ask_github_and_does_not_guess(tmp_path, capsys):
    root = repo(tmp_path, tags=("v0.12.0",))
    git(root, "remote", "set-url", "origin", str(tmp_path / "nowhere.git"))
    before = installer(root)
    assert run(root, "0.12.0") == 1
    assert "could not ask GitHub" in capsys.readouterr().err and installer(root) == before


def test_no_check_is_for_working_offline_and_every_other_rule_still_applies(tmp_path, capsys):
    root = repo(tmp_path, origin=False)
    assert run(root, "0.12.0", "--no-check") == 0 and 'VERSION="0.12.0"' in installer(root)
    assert run(root, "0.99.0", "--no-check") == 1  # ahead of the code: still refused
    assert "ahead of this code" in capsys.readouterr().err


@pytest.mark.parametrize("new, why", [("0.10.6", "an app never downgrades"), ("0.13.0", "ahead of this code"), ("0.11", "not a version"), ("v0.12.0", "not a version"), ("", "not a version")])
def test_it_refuses_a_version_that_goes_backwards_is_ahead_of_the_code_or_is_not_a_version(tmp_path, capsys, new, why):
    root = repo(tmp_path, tags=("v0.10.6", "v0.13.0", "v0.12.0"), entries=("0.13.0", "0.12.0", "0.11.0", "0.10.6"))
    before = installer(root)
    assert run(root, new) == 1
    assert why in capsys.readouterr().err and installer(root) == before


def test_it_refuses_a_version_with_no_changelog_entry_because_the_release_notes_come_from_there(tmp_path, capsys):
    root = repo(tmp_path, entries=("0.11.0",), tags=("v0.11.0", "v0.12.0"))
    assert run(root, "0.12.0") == 1 and "no entry for 0.12.0" in capsys.readouterr().err


def test_asking_for_what_is_already_advertised_changes_nothing_and_succeeds(tmp_path, capsys):
    root = repo(tmp_path)
    before = installer(root)
    assert run(root, "0.11.0") == 0 and installer(root) == before
    assert "nothing to change" in capsys.readouterr().out


def test_it_will_not_edit_an_installer_that_has_no_single_version_line(tmp_path, capsys):
    root = repo(tmp_path)
    (root / "site" / "public" / "install.sh").write_text("echo no version here\n", encoding="utf-8")
    assert run(root, "0.12.0", "--no-check") == 1 and "found 0" in capsys.readouterr().err
