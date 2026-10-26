#!/usr/bin/env python3
"""Print one version's entry from maintenance/CHANGELOG.md, to use as a GitHub release's notes.

    python3 maintenance/tools/release_notes.py 0.10.45 [--changelog PATH]

The entry is everything under its `## [X.Y.Z] - date` heading up to the next `## [` heading. Exit 2 (and nothing on stdout) if there is no such entry:
a release must never go out with someone else's notes or none.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
PRODUCT = "Function_2_C_Decompiler"
# a release may be named: `## [0.11.0] - 2026-10-23 - ROMday`. A name is ordinary words (letters, digits, spaces, . _ ' -), at most 40 characters, so that it
# can travel through a title file and a shell command with nothing in it for either to expand.
NAME = r"([A-Za-z0-9][A-Za-z0-9 ._'-]{0,39})"


def release_name(changelog: str, version: str) -> str | None:
    m = re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}} - {NAME}$", changelog, re.M)
    return m.group(1).strip() if m else None


def title(changelog: str, version: str) -> str:
    name = release_name(changelog, version)
    return f"{PRODUCT} {version}" + (f" - {name}" if name else "")


def section(changelog: str, version: str) -> str | None:
    head = re.search(rf"^## \[{re.escape(version)}\] - .*$", changelog, re.M)
    if head is None:
        return None
    rest = changelog[head.end():]
    nxt = re.search(r"^## \[", rest, re.M)
    body = (rest[: nxt.start()] if nxt else rest).strip()
    return body + "\n" if body else None


def main(argv: list[str]) -> int:
    path = CHANGELOG
    if "--changelog" in argv:
        i = argv.index("--changelog")
        path = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    want_title = "--title" in argv
    argv = [a for a in argv if a != "--title"]
    if len(argv) != 1:
        print("usage: release_notes.py VERSION [--title] [--changelog PATH]", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    found = section(text, argv[0])
    if found is None:
        print(f"no changelog entry for {argv[0]} in {path}", file=sys.stderr)
        return 2
    sys.stdout.write(title(text, argv[0]) + "\n" if want_title else found)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
