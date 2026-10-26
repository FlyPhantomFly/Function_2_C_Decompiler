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
    if len(argv) != 1:
        print("usage: release_notes.py VERSION [--changelog PATH]", file=sys.stderr)
        return 2
    found = section(path.read_text(encoding="utf-8"), argv[0])
    if found is None:
        print(f"no changelog entry for {argv[0]} in {path}", file=sys.stderr)
        return 2
    sys.stdout.write(found)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
