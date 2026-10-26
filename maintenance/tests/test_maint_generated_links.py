"""What the app writes into other people's projects must point at this fork, not at upstream's website.

An exported decompilation is handed to strangers. Its README says what it was started with and what the build needs, and its
`build.py` says, when decomp.wtf is missing, where to get it. Upstream's text sent them to `https://decomp.wtf`, the website
of a project that is not this one and that serves upstream's installer. These tests pin that every such sentence names this
fork's repository, take the build scripts through their real failure path, and scan the source for the old address.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import decompnet
from decompnet.rom import export, export_gba

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decompnet"
HOME = "https://github.com/FlyPhantomFly/Function_2_C_Decompiler"
SCRIPTS = ["export_build.py", "export_gba_build.py"]


def test_the_package_names_where_it_comes_from_and_what_it_is_a_fork_of():
    assert decompnet.HOME_URL == HOME
    assert decompnet.UPSTREAM_URL == "https://github.com/i12bp8/decomp.wtf"


def test_no_shipped_file_links_to_upstreams_website():
    hits = []
    for path in SRC.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".md", ".toml", ".js", ".html", ".json", ".sh"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{path.relative_to(ROOT)}:{n}" for n, line in enumerate(text.splitlines(), 1)
                     if "https://decomp.wtf" in line or "http://decomp.wtf" in line]
    assert hits == [], hits


def _readme(tmp_path: Path) -> str:
    return (tmp_path / "README.md").read_text(encoding="utf-8")


def test_an_exported_n64_or_psx_readme_links_this_fork_and_says_where_to_get_the_tool(tmp_path):
    export._write_docs(tmp_path, "Demo Quest", "n64", "baserom.z64", 3, 10, [])
    text = _readme(tmp_path)
    assert f"started with [Function_2_C_Decompiler]({HOME})" in text
    assert f"needs Function_2_C_Decompiler installed from {HOME}" in text
    assert "https://decomp.wtf" not in text


def test_an_exported_gba_readme_links_this_fork_and_says_where_to_get_the_tool(tmp_path):
    export_gba._docs(tmp_path, "Demo Quest", 3, 10, [])
    text = _readme(tmp_path)
    assert f"started with [Function_2_C_Decompiler]({HOME})" in text
    assert f"needs Function_2_C_Decompiler installed from {HOME}" in text
    assert "https://decomp.wtf" not in text


@pytest.mark.parametrize("name", ["scratch_dtk.py", "scratch_dsd.py"])
def test_the_fork_mode_scratch_readmes_link_this_fork(name):
    text = (SRC / "forks" / name).read_text(encoding="utf-8")
    assert "Started from scratch with [Function_2_C_Decompiler]({HOME_URL})" in text and "HOME_URL" in text


def _python_without_decompnet() -> str | None:
    """A Python that has not got this package: what someone who just received an exported project has."""
    # Not simply `python3` from PATH: under `uv run` that is this project's own virtualenv, which has the package.
    for exe in ("/usr/bin/python3", "/usr/local/bin/python3", "/bin/python3", shutil.which("python3")):
        if exe and Path(exe).exists() and subprocess.run([exe, "-I", "-c", "import decompnet"], capture_output=True).returncode != 0:
            return exe
    return None


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_build_script_tells_a_stranger_where_to_get_the_tool(name, tmp_path):
    exe = _python_without_decompnet()
    if exe is None:
        pytest.skip("needs a python3 on PATH that cannot import decompnet")
    script = tmp_path / "build.py"
    shutil.copy(SRC / "rom" / name, script)  # how the exporter puts it into a generated project...
    (tmp_path / "build.json").write_text("{}", encoding="utf-8")  # ...beside the build.json it reads before it checks for the tool
    done = subprocess.run([exe, "-I", str(script)], capture_output=True, text=True, timeout=60, cwd=tmp_path)
    assert done.returncode != 0
    assert f"install Function_2_C_Decompiler first ({HOME})" in done.stderr
    assert "https://decomp.wtf" not in done.stderr


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_build_scripts_cannot_import_the_constant_so_their_literal_must_match_it(name):
    """They run where decompnet is missing, which is exactly when the message matters: the URL is spelled out."""
    text = (SRC / "rom" / name).read_text(encoding="utf-8")
    assert text.count(HOME) == 2  # the docstring and the message
    assert decompnet.HOME_URL == HOME
