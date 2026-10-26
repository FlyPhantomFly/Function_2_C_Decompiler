#!/usr/bin/env python3
"""Bump this fork's version everywhere it must agree, or check that it already does.

    python3 maintenance/tools/bump_version.py 0.10.8      # bump all three places to 0.10.8
    python3 maintenance/tools/bump_version.py --check     # exit 1 unless all three agree

The version lives in three places that have to match, or `uv sync --locked` fails and the app reports the wrong version:
  pyproject.toml              version = "X.Y.Z"           (the package's metadata)
  src/decompnet/__init__.py   __version__ = "X.Y.Z"       (what the app and the updater report)
  uv.lock                     the `decompnet` package's own version line

Not touched on purpose (see maintenance/README.md): site/public/install.sh and install.ps1 (their VERSION names a wheel
that has to exist on a server, so it only moves when a release is really published) and the Claude plugin manifests
(a separate version track).

Fork versions are plain increments of upstream's 0.10.x line, because updates.version_key compares only the first
three numbers; a suffix like `-fork.1` would be ignored by it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "src" / "decompnet" / "__init__.py"
LOCK = ROOT / "uv.lock"

SEMVER = re.compile(r"\d+\.\d+\.\d+")
# each: (file, pattern whose group 2 is the version; groups 1 and 3 are kept)
PLACES = {
    "pyproject.toml": (PYPROJECT, re.compile(r'(^version = ")([^"]+)(")', re.M)),
    "src/decompnet/__init__.py": (INIT, re.compile(r'(^__version__ = ")([^"]+)(")', re.M)),
    "uv.lock": (LOCK, re.compile(r'(\[\[package\]\]\nname = "decompnet"\nversion = ")([^"]+)(")')),
}


def key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def read_versions() -> dict[str, str]:
    """The version each place declares. Raises if a place doesn't have exactly one declaration."""
    found = {}
    for name, (path, pattern) in PLACES.items():
        matches = pattern.findall(path.read_text(encoding="utf-8"))
        if len(matches) != 1:
            raise SystemExit(f"{name}: expected exactly one version declaration, found {len(matches)}")
        found[name] = matches[0][1]
    return found


def bump(new: str) -> None:
    if not SEMVER.fullmatch(new):
        raise SystemExit(f"{new!r} is not a plain X.Y.Z version")
    versions = read_versions()
    if len(set(versions.values())) != 1:
        raise SystemExit(f"refusing to bump: the three places already disagree: {versions}")
    current = next(iter(versions.values()))
    if key(new) <= key(current):
        raise SystemExit(f"{new} is not newer than the current version {current}")
    for name, (path, pattern) in PLACES.items():
        text = path.read_text(encoding="utf-8")
        updated, n = pattern.subn(lambda m: f"{m.group(1)}{new}{m.group(3)}", text)
        if n != 1:  # read_versions already proved this; belt and braces before writing
            raise SystemExit(f"{name}: expected one replacement, made {n}")
        path.write_text(updated, encoding="utf-8")
        print(f"{name}: {current} -> {new}")
    if after := read_versions():
        assert set(after.values()) == {new}, after
    try:  # uv itself is the judge of whether the lock still matches the project
        done = subprocess.run(["uv", "lock", "--check"], cwd=ROOT, capture_output=True, text=True)
    except FileNotFoundError:
        print("uv not found: run `uv lock --check` yourself before committing")
        return
    if done.returncode != 0:
        raise SystemExit("uv lock --check failed after the bump:\n" + (done.stderr or done.stdout))
    print("uv lock --check: ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--check"]:
        versions = read_versions()
        print(versions)
        sys.exit(0 if len(set(versions.values())) == 1 else 1)
    if len(args) != 1:
        sys.exit(__doc__)
    bump(args[0])
