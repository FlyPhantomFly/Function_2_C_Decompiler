"""The GUI's script must at least parse.

The Python tests read `app.js` as text, so a syntax error in it (a variable declared twice, a missing bracket) passes every one of them and then the whole GUI
fails to load. That happened while adding the per-provider subtotals (a `const names` clashing with one a few lines up); `node --check` caught it and 135 Python
tests had not. So when Node is available this runs the syntax check on every script the GUI ships. Without Node the test is skipped, with its reason.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "decompnet" / "app" / "static"
SCRIPTS = sorted(STATIC.glob("*.js"))


def test_there_are_gui_scripts_to_check():
    assert [p.name for p in SCRIPTS] and "app.js" in [p.name for p in SCRIPTS]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js (`node --check`)")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_every_gui_script_parses(script):
    done = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr.strip().splitlines()[:6]
