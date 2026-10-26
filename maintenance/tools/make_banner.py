#!/usr/bin/env python3
"""Render the README banner (light and dark) from its source, maintenance/assets/banner.html.

    CHROME=/path/to/chrome python3 maintenance/tools/make_banner.py [OUTPUT_DIR]      # default: .github/assets

The banner is HTML so it can be edited and re-rendered rather than being an image nobody can change. It is drawn at 1280 x 400 CSS pixels and written at 2x
(2560 x 800), the size the README expects. See maintenance/tools/screenshot_ui.py for where to get a headless Chromium.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "maintenance" / "assets" / "banner.html"
SIZE = (1280, 400)
SCALE = 2


def render_command(chrome: str, theme: str, out: Path) -> list[str]:
    url = SOURCE.as_uri() + ("#dark" if theme == "dark" else "")
    return [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
            f"--window-size={SIZE[0]},{SIZE[1]}", f"--force-device-scale-factor={SCALE}", "--virtual-time-budget=4000", f"--screenshot={out}", url]


def png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def main(argv: list[str]) -> int:
    chrome = os.environ.get("CHROME", "")
    if not chrome or not Path(chrome).exists():
        print("set CHROME to a Chromium binary (see maintenance/tools/screenshot_ui.py)", file=sys.stderr)
        return 2
    out = Path(argv[0]) if argv else ROOT / ".github" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("light", "dark"):
        target = out / f"banner-{theme}.png"
        target.unlink(missing_ok=True)
        subprocess.run(render_command(chrome, theme, target), capture_output=True, timeout=120)
        if not target.exists() or png_size(target) != (SIZE[0] * SCALE, SIZE[1] * SCALE):
            print(f"{theme}: no banner of {SIZE[0] * SCALE}x{SIZE[1] * SCALE} was written", file=sys.stderr)
            return 1
        print(f"{target}: {png_size(target)[0]}x{png_size(target)[1]}, {target.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
