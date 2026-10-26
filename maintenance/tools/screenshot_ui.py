#!/usr/bin/env python3
"""Screenshot the app's GUI at a desktop and a phone width with a headless Chromium: how to check a UI change you cannot see.

    CHROME=/path/to/chrome python3 maintenance/tools/screenshot_ui.py [OUTPUT_DIR]      # default: maintenance/baseline/ui

It starts the app on a free port with a throwaway home folder and update checks off, loads its page (the app sets a session cookie
and redirects, which a headless browser follows), writes `desktop.png` and `phone.png`, and stops the app by its process id.

A browser is not a dependency of this project. One that works in a bare container is the portable build of ungoogled-chromium from
GitHub releases (`ungoogled-software/ungoogled-chromium-portablelinux`, the `x86_64_linux.tar.xz`): unpack it and point CHROME at its
`chrome`. GitHub shows a sha256 beside each release asset; compare it with `sha256sum` before running the file. Running as root needs
`--no-sandbox` (this tool passes it): use it only on the app's own localhost page, as here.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIDTHS = {"desktop": (1280, 800), "phone": (420, 860)}
PNG = b"\x89PNG\r\n\x1a\n"


def screenshot_command(chrome: str, url: str, out: Path, size: tuple[int, int]) -> list[str]:
    return [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", f"--window-size={size[0]},{size[1]}",
            "--virtual-time-budget=6000", f"--screenshot={out}", url]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_app(home: Path, port: int) -> tuple[subprocess.Popen, str]:
    env = {**os.environ, "DECOMP_HOME": str(home), "DECOMP_UPDATES": "off"}
    proc = subprocess.Popen([sys.executable, "-m", "decompnet.app.cli", "--no-browser", "--port", str(port)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if m := re.search(r"http://127\.0\.0\.1:\d+/\?k=[\w-]+", line or ""):
            return proc, m.group(0)
        if proc.poll() is not None:
            break
    proc.kill()
    raise SystemExit("the app did not print its address within 30 s")


def main(argv: list[str]) -> int:
    chrome = os.environ.get("CHROME", "")
    if not chrome or not Path(chrome).exists():
        print("set CHROME to a Chromium binary (see this file's docstring)", file=sys.stderr)
        return 2
    out = Path(argv[0]) if argv else ROOT / "maintenance" / "baseline" / "ui"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as home:
        proc, url = start_app(Path(home), free_port())
        try:
            for name, size in WIDTHS.items():
                target = out / f"{name}.png"
                target.unlink(missing_ok=True)
                subprocess.run(screenshot_command(chrome, url, target, size), capture_output=True, timeout=120)
                if not target.exists() or not target.read_bytes().startswith(PNG):
                    print(f"no screenshot for {name}", file=sys.stderr)
                    return 1
                print(f"{target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}: {size[0]}x{size[1]}, {target.stat().st_size} bytes")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
