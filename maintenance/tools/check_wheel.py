#!/usr/bin/env python3
"""Check that a built wheel is complete and clean: what a release would ship.

    uv build --wheel --out-dir dist && python3 maintenance/tools/check_wheel.py dist/*.whl [--version 0.10.45]

A wheel can look fine and be useless: package data that is not inside the package (the GUI, the agents' guides, the compiler registry, the demo ROM)
is silently left out, and then the installed app has no page to show. This lists what the app cannot run without and what must never ship, and
checks the metadata. With no --version it uses the one in pyproject.toml. Exit 1 and one line per problem if anything is wrong.
"""

from __future__ import annotations

import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = [
    "decompnet/__init__.py", "decompnet/toolchains.toml", "decompnet/app/cli.py", "decompnet/app/server.py",
    "decompnet/app/static/index.html", "decompnet/app/static/app.js", "decompnet/app/static/app.css",
    "decompnet/app/static/demo/demo-quest-64.z64", "decompnet/forks/ghidra_scripts/DecompWtfExport.java",
]
MIN_GUIDES = 20  # the agents' knowledge base (app/guide/*.md): 21 today
ENTRY_POINT = "decomp = decompnet.app.cli:main"
FORBIDDEN = re.compile(r"(^|/)(tests?|maintenance|projects|site|docs|\.github|\.venv)/|__pycache__|\.pyc$|\.sqlite$|\.bak-v|before-restore|junit\.xml|settings\.json|\.env$")


def problems(wheel: Path, version: str | None = None) -> list[str]:
    try:
        z = zipfile.ZipFile(wheel)
    except (zipfile.BadZipFile, OSError) as e:
        return [f"{Path(wheel).name} cannot be read as a wheel: {e}"]
    names = set(z.namelist())
    out = [f"missing: {need}" for need in REQUIRED if need not in names]
    guides = [n for n in names if n.startswith("decompnet/app/guide/") and n.endswith(".md")]
    if len(guides) < MIN_GUIDES:
        out.append(f"only {len(guides)} agent guides (decompnet/app/guide/*.md), expected at least {MIN_GUIDES}")
    out += [f"should not ship: {n}" for n in sorted(names) if FORBIDDEN.search(n)]
    metadata = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
    if metadata is None:
        out.append("no METADATA")
    else:
        text = z.read(metadata).decode("utf-8", "replace")
        if not re.search(r"^Name: decompnet$", text, re.M):
            out.append("the package name is not decompnet")
        if version and not re.search(rf"^Version: {re.escape(version)}$", text, re.M):
            out.append(f"the wheel's version is not {version}")
    entry = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
    if entry is None or ENTRY_POINT not in z.read(entry).decode("utf-8", "replace"):
        out.append(f"the `decomp` command is not declared ({ENTRY_POINT})")
    if not any(n.endswith("/licenses/LICENSE") or n.endswith(".dist-info/LICENSE") for n in names):
        out.append("the LICENSE file is not in the wheel")
    return out


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--version")]
    version = None
    if "--version" in argv:
        version = argv[argv.index("--version") + 1]
        args = [a for a in args if a != version]
    if not args:
        print("usage: check_wheel.py WHEEL [--version X.Y.Z]", file=sys.stderr)
        return 2
    version = version or tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    bad = 0
    for wheel in args:
        found = problems(Path(wheel), version)
        for line in found:
            print(f"{Path(wheel).name}: {line}")
        bad += len(found)
        if not found:
            print(f"{Path(wheel).name}: OK ({len(zipfile.ZipFile(wheel).namelist())} files, version {version})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
