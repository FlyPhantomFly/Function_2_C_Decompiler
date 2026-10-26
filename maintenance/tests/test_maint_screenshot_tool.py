"""The tool that lets a maintainer see the GUI after changing it (see maintenance/tools/screenshot_ui.py).

The command it builds is checked anywhere. Running it for real needs a Chromium binary, which is not a dependency of this project, so
that test runs only when CHROME points at one; the layout of the committed screenshots is what a person looks at.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("screenshot_ui", ROOT / "maintenance" / "tools" / "screenshot_ui.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load()


def test_the_command_loads_the_page_headless_at_the_requested_size_and_writes_the_file(tmp_path):
    cmd = tool.screenshot_command("/x/chrome", "http://127.0.0.1:1/?k=a", tmp_path / "p.png", (420, 860))
    assert cmd[0] == "/x/chrome" and "--headless=new" in cmd and "--window-size=420,860" in cmd
    assert f"--screenshot={tmp_path / 'p.png'}" in cmd and cmd[-1] == "http://127.0.0.1:1/?k=a"


def test_it_covers_a_desktop_and_a_phone_width_and_the_phone_is_the_one_the_sidebar_tolerance_is_for():
    assert tool.WIDTHS["desktop"][0] >= 1024 and tool.WIDTHS["phone"][0] <= 480


def test_it_refuses_politely_without_a_browser(monkeypatch, capsys):
    monkeypatch.delenv("CHROME", raising=False)
    assert tool.main([]) == 2
    assert "set CHROME" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("CHROME") or not Path(os.environ.get("CHROME", "")).exists(), reason="needs CHROME=<a Chromium binary>")
def test_it_starts_the_app_takes_both_screenshots_and_stops_the_app(tmp_path):
    assert tool.main([str(tmp_path)]) == 0
    for name in ("desktop", "phone"):
        assert (tmp_path / f"{name}.png").read_bytes().startswith(tool.PNG)
