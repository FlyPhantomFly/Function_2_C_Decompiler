#!/usr/bin/env python3
"""Repaint the title bar of the README's animated demo with the product's name.

`.github/assets/demo.webp` is a scripted playback of the interface that was recorded from a page on the original project's website; that page is not in this repository, so the animation cannot be
regenerated. Its title bar read "decomp.wtf / Demo Quest 64". This renders the new title with Chromium and the app's own font (Geist Mono), measured against the original's pixels
(size 11.2 px, weight 500, 65 px from the left), and composites it over every frame, leaving the rest of the frame and every frame's duration alone.

    CHROME=/path/to/chromium uv run --with pillow --with numpy python maintenance/tools/repaint_demo_title.py [--name NAME] [--out FILE]

It can be run again on its own output: the title area is cleared before the text is drawn.
"""

from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "src" / "decompnet" / "app" / "static" / "fonts" / "GeistMono-Variable.woff2"
DEMO = ROOT / ".github" / "assets" / "demo.webp"
# measured against the original title bar (see the docstring); the colours are the app's dark theme (--ink and --muted in app.css)
X0, TOP, W, H, LEFT, SIZE, WEIGHT = 58, 7, 308, 28, 65, 11.2, 500
INK, MUTED = (0xEC, 0xEB, 0xE5), (0x8E, 0x8A, 0x7F)
ROOT_TITLE = "Function_2_C_Decompiler"


def durations(path: Path) -> list[int]:
    """The duration of every frame, in ms, read from the animation chunks (Pillow does not report them for this file)."""
    data, out, pos = path.read_bytes(), [], 12
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if tag == b"ANMF":
            out.append(int.from_bytes(data[pos + 8 + 12:pos + 8 + 15], "little"))
        pos += 8 + size + (size & 1)
    return out


def masks(name: str, subtitle: str):
    """Two coverage masks (the name, and the rest of the title) rendered white-on-black by Chromium with the app's font."""
    import numpy as np
    from PIL import Image

    chrome = os.environ.get("CHROME")
    if not chrome:
        sys.exit("set CHROME to a Chromium binary (maintenance/tools/screenshot_ui.py says where to get one)")
    style = (f"@font-face{{font-family:'Geist Mono';src:url('file://{FONT}') format('woff2');font-weight:100 900}}body{{margin:0;background:#000}}"
             f".r{{height:{H}px;width:{W}px;position:relative;overflow:hidden}}.t{{position:absolute;left:{LEFT - X0}px;top:0;white-space:pre;color:#fff;"
             f"font:{WEIGHT} {SIZE}px/{H}px 'Geist Mono'}}.hide{{color:#000}}")
    html = (f"<!doctype html><meta charset=utf-8><style>{style}</style>"
            f"<div class=r><div class=t>{name}<span class=hide> / {subtitle}</span></div></div>"
            f"<div class=r><div class='t hide'>{name}<span style='color:#fff'> / {subtitle}</span></div></div>")
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "t.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", f"--window-size={W},{2 * H}",
                        f"--screenshot={tmp}/t.png", page.as_uri()], capture_output=True, timeout=60, check=True)
        shot = np.asarray(Image.open(Path(tmp) / "t.png").convert("L")).astype(float) / 255
    return shot[:H, :W], shot[H:2 * H, :W]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--name", default=ROOT_TITLE)
    ap.add_argument("--subtitle", default="Demo Quest 64")
    ap.add_argument("--src", type=Path, default=DEMO)
    ap.add_argument("--out", type=Path, default=DEMO)
    args = ap.parse_args(argv)
    import numpy as np
    from PIL import Image

    name_mask, rest_mask = masks(args.name, args.subtitle)
    src = Image.open(args.src)
    times = durations(args.src)
    frames = []
    for i in range(src.n_frames):
        src.seek(i)
        px = np.asarray(src.convert("RGB")).astype(float).copy()
        box = px[TOP:TOP + H, X0:X0 + W]
        bg = np.median(px[TOP:TOP + H, X0 + W:X0 + W + 16].reshape(-1, 3), axis=0)  # the bar's own colour in this frame, from beside the text
        box[:] = bg
        for mask, colour in ((name_mask, INK), (rest_mask, MUTED)):
            box[:] = box * (1 - mask[..., None]) + np.array(colour, dtype=float) * mask[..., None]
        frames.append(Image.fromarray(np.clip(px.round(), 0, 255).astype("uint8")))
    frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=times, loop=0, quality=90, method=4)
    print(f"{args.out}: {len(frames)} frames, {sum(times) / 1000:.1f} s, {args.out.stat().st_size / 1e6:.2f} MB; title now reads '{args.name} / {args.subtitle}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
