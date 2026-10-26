#!/usr/bin/env python3
"""Replace the product name `decomp.wtf` with `Function_2_C_Decompiler` where a person reads it, and nowhere else.

    python3 maintenance/tools/rename_product.py            # dry run: what would change, per file
    python3 maintenance/tools/rename_product.py --show     # ... and every changed line
    python3 maintenance/tools/rename_product.py --apply

Why not a find-and-replace: the string is also an identifier that existing projects and installs depend on (`.decomp.wtf.json`,
the logger name, Windows task and shortcut names), and it is the name of the ORIGINAL project wherever this fork credits it
(links to `github.com/i12bp8/decomp.wtf`, "upstream decomp.wtf"). Those are PROTECTED below and left exactly as they are. The
hyphenated forms (`decomp-wtf`: the WSL distro, the git branch, the Docker names, the localStorage keys, `/etc/decomp-wtf-runtime`)
are never touched, because this tool only looks for the dotted form. See maintenance/ARCHITECTURE.md, "Names".

Files it covers: the app (`src/`), the plugin, the README, compose and the Linux/Docker installer scripts. Not covered on purpose:
`projects/` (the demo projects write their credit string INTO the demo ROMs: `b"Demo Quest PS1 - made for decomp.wtf".ljust(40)` fills
a 40-byte header field, and the longer name would overflow it and corrupt the executable), the PowerShell installers (they refuse to
run: Windows is frozen), `maintenance/` (history and documentation about upstream), `tests/` (expectations are updated by hand when a
test says so), and `uv.lock`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = "decomp.wtf"
NEW = "Function_2_C_Decompiler"

# Left exactly as written. Each is an identifier something depends on, or a credit to the original project.
PROTECTED = [
    r"\.decomp\.wtf\.json",  # the project manifest that existing projects carry
    r"github\.com/i12bp8/decomp\.wtf",  # the original project's repository
    r"\[decomp\.wtf\]\(https://github\.com/i12bp8/decomp\.wtf\)",  # a credit link whose text is the original's name: the WHOLE link
    r"upstream decomp\.wtf|upstream's decomp\.wtf|the original decomp\.wtf",  # naming the original project
    r"the decomp\.wtf website|decomp\.wtf's website|https?://decomp\.wtf",  # the original's domain, which is not this product
    r"stop working on decomp\.wtf|didn't make decomp\.wtf",  # the original author's own notice in the README, kept as he wrote it
    r"getLogger\((?P<q>[\"'])decomp\.wtf(?P=q)\)",  # the logger's name (log files, configuration)
    r"decomp\.wtf\.(?:lnk|app)\b",  # Windows shortcut and macOS app file names (an existing install's files)
    r"RUN_NAME = \"decomp\.wtf\"",  # the Windows scheduled task's name (uninstall must find the old one)
    r"\"/TN\", \"decomp\.wtf\"",
    r"decomp\.wtf-installer",  # the PowerShell installers' user agent
    r"noreply@decomp\.wtf",  # replaced by hand: it is an address at a domain this fork does not own
]
_PROTECT = re.compile("|".join(f"(?:{p})" for p in PROTECTED))

INCLUDE_SUFFIXES = {".py", ".js", ".html", ".css", ".md", ".toml", ".json", ".sh", ".yml", ".svg"}
INCLUDE_EXACT = {"README.md", "docker-compose.yml", "pyproject.toml", "site/public/Dockerfile", "site/public/install.sh",
                 "site/public/dev.sh", "site/public/linux-base.sh"}
INCLUDE_PREFIXES = ("src/", "plugins/", ".claude-plugin/")
EXCLUDE_PREFIXES = ("src/decompnet/app/static/demo/", "maintenance/", "tests/")


SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".ruff_cache", ".pytest_cache"}


def _walk() -> list[str]:
    """Every file under the tree: what there is to look at when git cannot say (an unpacked zip has no .git)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        found += [(Path(dirpath) / f).relative_to(ROOT).as_posix() for f in filenames]
    return sorted(found)


def _listing() -> list[str]:
    """The tracked files when this is a git checkout; otherwise every file. Never an empty list: unpacked inside some other repository,
    `git ls-files` succeeds and names nothing here, and every check made on that list would pass over zero files."""
    try:
        listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _walk()
    listed = [n for n in listed if n]
    return listed if any(n.startswith("src/") for n in listed) else _walk()


def files() -> list[Path]:
    out = []
    for name in _listing():
        if not name or name.startswith(EXCLUDE_PREFIXES) or name.endswith(".ps1"):
            continue
        if name in INCLUDE_EXACT or (name.startswith(INCLUDE_PREFIXES) and Path(name).suffix in INCLUDE_SUFFIXES):
            out.append(ROOT / name)
    return out


def convert(text: str) -> str:
    """The text with the product name replaced everywhere except inside a protected span."""
    kept: list[str] = []

    def keep(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    protected = _PROTECT.sub(keep, text)
    renamed = protected.replace(OLD, NEW)
    return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], renamed)


def self_check() -> None:
    """Fail loudly if the protection ever damages what it exists to protect."""
    for sample in ("[decomp.wtf](https://github.com/i12bp8/decomp.wtf) by Sam", "see https://github.com/i12bp8/decomp.wtf/issues",
                   "from the decomp.wtf website", "read .decomp.wtf.json", 'logging.getLogger("decomp.wtf")', "upstream decomp.wtf"):
        assert convert(sample) == sample, f"protection failed: {sample!r} became {convert(sample)!r}"
    assert convert("decomp.wtf's tools") == f"{NEW}'s tools"
    assert "i12bp8/" + NEW not in convert("a [decomp.wtf](https://github.com/i12bp8/decomp.wtf) and decomp.wtf itself")


def main(argv: list[str]) -> int:
    self_check()
    apply, show = "--apply" in argv, "--show" in argv
    total_files = total_lines = 0
    for path in files():
        try:
            before = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        after = convert(before)
        if after == before:
            continue
        changed = [(i, a, b) for i, (a, b) in enumerate(zip(before.splitlines(), after.splitlines()), 1) if a != b]
        total_files += 1
        total_lines += len(changed)
        print(f"{path.relative_to(ROOT)}: {len(changed)} lines")
        if show:
            for i, a, b in changed:
                print(f"  {i}: {a.strip()[:150]}\n   -> {b.strip()[:150]}")
        if apply:
            path.write_text(after, encoding="utf-8")
    print(f"\n{total_lines} lines in {total_files} files {'changed' if apply else 'would change'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
