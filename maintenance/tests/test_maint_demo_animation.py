"""The README's animated demo carries the product's name, not the original project's.

The animation is a scripted playback recorded from a page on the original project's website that is not in this repository, so it cannot be regenerated: its title bar was repainted
(`maintenance/tools/repaint_demo_title.py`). These tests read the file's own chunks (no image library needed) to check that it is not the upstream file and kept its shape, and, where an image
library and a browser are available, that running the tool on the committed file changes nothing: if the title still carried the old name, that run would repaint it and the difference would be large.
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / ".github" / "assets" / "demo.webp"
UPSTREAM_SHA256 = "f5b30ed02ca1b9dd61f7167ad1b5fc1019262e50974944239220a6f1e16ce6f7"  # upstream's 0.10.6 file: 124 frames, 12.4 s, "decomp.wtf / Demo Quest 64"
sys.path.insert(0, str(ROOT / "maintenance" / "tools"))
import repaint_demo_title  # noqa: E402


def chunks(data: bytes):
    pos = 12
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        yield tag, data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)


def test_the_animation_is_not_upstreams_file_and_keeps_its_size_frames_timing_and_loop():
    data = DEMO.read_bytes()
    assert hashlib.sha256(data).hexdigest() != UPSTREAM_SHA256  # the old title is not still there
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    found = {tag: payload for tag, payload in chunks(data) if tag in (b"VP8X", b"ANIM")}
    canvas = (int.from_bytes(found[b"VP8X"][4:7], "little") + 1, int.from_bytes(found[b"VP8X"][7:10], "little") + 1)
    assert canvas == (960, 498) and struct.unpack_from("<H", found[b"ANIM"], 4)[0] == 0  # the same canvas, looping forever
    times = repaint_demo_title.durations(DEMO)
    assert len(times) == 124 and sum(times) == 12400  # every frame, and the timing the original had


def test_the_readme_shows_this_animation_and_says_what_it_is():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert ".github/assets/demo.webp" in readme and DEMO.exists()


needs_tools = pytest.mark.skipif(not os.environ.get("CHROME"), reason="needs CHROME (a Chromium binary) and Pillow and numpy: `uv run --with pillow --with numpy`")


@needs_tools
def test_running_the_repaint_tool_on_the_committed_animation_changes_nothing_so_its_title_is_already_the_new_one(tmp_path):
    np = pytest.importorskip("numpy")
    image = pytest.importorskip("PIL.Image")
    out = tmp_path / "again.webp"
    assert repaint_demo_title.main(["--src", str(DEMO), "--out", str(out)]) == 0
    a, b = image.open(DEMO), image.open(out)
    assert a.n_frames == b.n_frames == 124
    top, left, width, height = repaint_demo_title.TOP, repaint_demo_title.X0, repaint_demo_title.W, repaint_demo_title.H
    worst = 0.0
    for i in range(0, a.n_frames, 8):
        a.seek(i)
        b.seek(i)
        x, y = np.asarray(a.convert("RGB")).astype(float), np.asarray(b.convert("RGB")).astype(float)
        worst = max(worst, float(np.abs(x - y)[top:top + height, left:left + width].mean()))
    assert worst < 3, worst  # upstream's file differs by about 18 here: its title would be repainted


def test_the_tool_refuses_to_run_without_a_browser_and_says_what_to_set(monkeypatch):
    pytest.importorskip("numpy")
    monkeypatch.delenv("CHROME", raising=False)
    with pytest.raises(SystemExit, match="set CHROME"):
        repaint_demo_title.masks("x", "y")
