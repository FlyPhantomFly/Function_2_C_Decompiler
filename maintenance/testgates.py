"""Skip conditions shared by the tests that build the demo ROMs, so a missing tool is a skip with a reason and not an
error from deep inside a build script.

Why this exists: on a machine with some of the tools, upstream's tests errored instead of skipping. The demo-ROM build
scripts need `llvm-objcopy` (the gates checked only `ld.lld`) and zlib's source (fetched by
`projects/zlib-n64/prepare.py`; nothing checked it). See maintenance/baseline/README.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from decompnet import toolchains

ROOT = Path(__file__).resolve().parents[1]
ZLIB_SOURCE = ROOT / "projects" / "zlib-n64" / "original" / "zlib.h"


def demo_rom_problem(toolchain: str = "gcc-2.7.2-kmc") -> str:
    """Why a demo ROM can't be built on this machine, in words for a skip message; "" when it can."""
    missing = []
    if toolchains.installed(toolchain) is None:
        missing.append(toolchain)
    missing += [tool for tool in ("ld.lld", "llvm-objcopy") if not shutil.which(tool)]
    if not ZLIB_SOURCE.exists():
        missing.append("zlib's source (run: python3 -I projects/zlib-n64/prepare.py)")
    return f"needs {', '.join(missing)} to build the demo ROM" if missing else ""
