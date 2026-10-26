#!/usr/bin/env python3
"""Move the installer's VERSION to a release that has been published.

`site/public/install.sh` carries a `VERSION="X.Y.Z"` line, and two things read it from `main`: the installer (piped from curl it installs the tag `vX.Y.Z`) and every installed app's updater
(it offers an update when X.Y.Z is newer than the app). So it must only ever name a release that EXISTS, and it is moved AFTER the release is published, never before: otherwise, in the minutes
between the push and the tag, every updater would be pointed at a download that does not exist yet. This is the one step that moves it, and it refuses unless:

  - X.Y.Z is a plain version, not lower than the one there now (an app never downgrades), and not ahead of the code (this package's own version);
  - the changelog has an entry for it (the release notes come from there); and
  - the tag `vX.Y.Z` exists on `origin` on GitHub (skip with --no-check only to work offline).

    python3 maintenance/tools/set_install_version.py 0.12.0     then commit and push the one changed line
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINE = re.compile(r'^VERSION="([^"]*)"$', re.M)
PLAIN = re.compile(r"^\d+\.\d+\.\d+$")


def key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("version")
    ap.add_argument("--no-check", action="store_true", help="do not ask GitHub whether the tag exists (offline work only)")
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root, new = args.root, args.version
    installer = root / "site" / "public" / "install.sh"

    def refuse(why: str) -> int:
        print(f"refused: {why}", file=sys.stderr)
        return 1

    if not PLAIN.match(new):
        return refuse(f"{new!r} is not a version like 0.12.0")
    text = installer.read_text(encoding="utf-8")
    found = LINE.findall(text)
    if len(found) != 1:
        return refuse(f"expected one VERSION line in {installer}, found {len(found)}")
    current = found[0]
    package = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    if key(new) < key(current):
        return refuse(f"{new} is lower than {current}, which is advertised now: an app never downgrades")
    if key(new) > key(package):
        return refuse(f"{new} is ahead of this code ({package}): the installer must not advertise what has not been written")
    if not re.search(rf"^## \[{re.escape(new)}\] - ", (root / "maintenance" / "CHANGELOG.md").read_text(encoding="utf-8"), re.M):
        return refuse(f"the changelog has no entry for {new}: the release notes come from there")
    if not args.no_check:
        done = subprocess.run(["git", "ls-remote", "--tags", "origin", f"refs/tags/v{new}"], cwd=root, capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            return refuse(f"could not ask GitHub whether the tag v{new} exists ({done.stderr.strip() or 'no answer'}); use --no-check only if you are offline and sure")
        if not done.stdout.strip():
            return refuse(f"the tag v{new} does not exist on origin yet: publish the release first (push the tag and wait for the Release workflow), then run this")
    if new == current:
        print(f"install.sh already advertises {new}; nothing to change")
        return 0
    installer.write_text(LINE.sub(f'VERSION="{new}"', text, count=1), encoding="utf-8")
    print(f"install.sh VERSION: {current} -> {new}. Commit and push that one line; from then on installers and updated apps get {new}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
