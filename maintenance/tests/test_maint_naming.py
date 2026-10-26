"""The product is called Function_2_C_Decompiler. Its identifiers are not renamed, and the original project keeps its own name.

Three kinds of "decomp.wtf" were in the code, and a find-and-replace gets two of them wrong:

  1. the product's name, where a person reads it (the UI, messages, READMEs, agent prompts): renamed;
  2. identifiers that existing projects and installs depend on (`.decomp.wtf.json`, the logger, Windows task and shortcut names,
     and every hyphenated form: the WSL distro, the git branch, the Docker names, the browser storage keys): left exactly as they
     are, because renaming them orphans what users already have;
  3. the name of the ORIGINAL project, wherever this fork credits it (links to its repository, its author's own notice): left alone.

`maintenance/tools/rename_product.py` does the renaming with the second and third kinds protected. These tests pin all three, and a
trap found while writing the tool: the demo builders put a credit string into fixed-width ROM header fields.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import decompnet

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decompnet"
NEW = "Function_2_C_Decompiler"
UPSTREAM = "https://github.com/i12bp8/decomp.wtf"


def _tool():
    spec = importlib.util.spec_from_file_location("rename_product", ROOT / "maintenance" / "tools" / "rename_product.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _tool()


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---- the product name --------------------------------------------------------------------------------------------------------


def test_the_package_names_the_product_and_a_commit_address_nobody_can_mistake_for_a_real_one():
    assert decompnet.PRODUCT == NEW
    assert decompnet.NOREPLY_EMAIL.endswith(".invalid") and "decomp.wtf" not in decompnet.NOREPLY_EMAIL  # RFC 2606: never resolves


def test_no_covered_file_still_has_the_old_name_outside_a_protected_span():
    """Re-running the tool changes nothing: every remaining `decomp.wtf` is an identifier or a credit the tool is built to keep."""
    leftovers = []
    for path in tool.files():
        text = path.read_text(encoding="utf-8")
        if tool.convert(text) != text:
            leftovers.append(str(path.relative_to(ROOT)))
    assert leftovers == []


def test_the_tools_protection_never_damages_what_it_protects():
    tool.self_check()


def test_the_app_window_the_wordmark_and_the_page_title_say_the_new_name():
    html = read("src/decompnet/app/static/index.html")
    assert "<title>Function_2_C_Decompiler</title>" in html
    assert html.count("<span>Function_2_C_<b>Decompiler</b></span>") == 2  # the sidebar and the narrow-screen header
    assert "decomp<b>.wtf" not in html
    css = read("src/decompnet/app/static/app.css")
    brand = css[css.index(".brand {"): css.index("}", css.index(".brand {"))]
    assert "min-width: 0" in brand and "13px" in brand  # a 23-character name must not push the layout out of the 248px sidebar
    assert "overflow-wrap" in css[css.index(".brand span"): css.index(".brand span") + 80]


def test_the_agents_are_told_what_they_work_in_by_the_new_name():
    tools = read("src/decompnet/app/tools.py")
    assert f'title="{NEW}"' in tools and "You are a decompilation agent in Function_2_C_Decompiler" in tools
    assert 'name="decomp"' in tools  # the identifier agents' configurations use is unchanged


# ---- the commit identity ------------------------------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_commits_the_app_makes_with_no_git_identity_are_signed_by_the_product_with_no_foreign_address(tmp_path, monkeypatch):
    from decompnet.forks import project

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    project._git_env.cache_clear()
    env = project._git_env(repo)
    assert env is not None
    (repo / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "made by the app"], cwd=repo, env=env, check=True)
    who = subprocess.run(["git", "log", "-1", "--format=%an|%ae|%cn|%ce"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert who == f"{NEW}|{decompnet.NOREPLY_EMAIL}|{NEW}|{decompnet.NOREPLY_EMAIL}"
    project._git_env.cache_clear()


def test_the_scratch_project_commits_use_the_same_identity_not_an_address_at_the_original_domain():
    for name in ("scratch_dsd.py", "scratch_dtk.py"):
        text = read(f"src/decompnet/forks/{name}")
        assert 'f"user.name={PRODUCT}"' in text and 'f"user.email={NOREPLY_EMAIL}"' in text
        assert "noreply@decomp.wtf" not in text


# ---- identifiers that must NOT change ---------------------------------------------------------------------------------------------

KEPT = [
    ("src/decompnet/forks/project.py", '.decomp.wtf.json', "the project manifest existing projects carry"),
    ("src/decompnet/forks/project.py", 'STATE = ".decomp-wtf"', "the state folder inside a fork"),
    ("src/decompnet/app/forkengine.py", '"-b", "decomp-wtf"', "the git branch created in a fork"),
    ("src/decompnet/app/forkengine.py", ".decomp.wtf.json", "the manifest written for a project"),
    ("src/decompnet/hostenv.py", 'Path("/etc/decomp-wtf-runtime")', "the runtime marker written by linux-base.sh"),
    ("src/decompnet/hostenv.py", '"decomp-wtf"', "the WSL distribution and Docker container name"),
    ("src/decompnet/app/server.py", '"app": "decomp-wtf"', "the /health answer processes recognise each other by"),
    ("src/decompnet/app/cli.py", '== "decomp-wtf"', "the check on that answer"),
    ("src/decompnet/app/static/app.js", 'THEME_KEY = "decomp-wtf-theme"', "a browser storage key: renaming it resets everyone's theme"),
    ("src/decompnet/app/static/app.js", 'UPDATE_SKIP = "decomp-wtf-skip-update"', "a browser storage key"),
    ("src/decompnet/app/service.py", 'RUN_NAME = "decomp.wtf"', "the Windows scheduled task: uninstall must find the old one"),
    ("src/decompnet/app/service.py", '"decomp-wtf.service"', "the systemd unit name"),
    ("src/decompnet/app/launcher.py", "decomp.wtf.lnk", "the Windows shortcut file"),
    ("src/decompnet/app/launcher.py", "decomp.wtf.app", "the macOS app bundle"),
    ("src/decompnet/app/agents.py", 'getLogger("decomp.wtf")', "the logger the app writes its log file from"),
    ("docker-compose.yml", "container_name: decomp-wtf", "the container"),
    ("site/public/linux-base.sh", "/etc/decomp-wtf-runtime", "the marker the app reads"),
    (".claude-plugin/marketplace.json", '"name": "decomp-wtf"', "the name /plugin install decomp-wtf@decomp-wtf uses"),
]


@pytest.mark.parametrize("path, needle, why", KEPT)
def test_an_identifier_other_things_depend_on_is_unchanged(path, needle, why):
    assert needle in read(path), f"{path}: {why}"


# ---- the original project keeps its name --------------------------------------------------------------------------------------------


def test_the_original_authors_notice_is_exactly_as_he_wrote_it():
    readme = read("README.md")
    assert "I've decided to stop working on decomp.wtf and archive it." in readme
    assert "I didn't make decomp.wtf to do any harm" in readme
    assert "stop working on Function_2_C_Decompiler" not in readme  # his words about his project are not rewritten


def test_every_credit_link_to_the_original_project_is_intact_and_none_is_damaged():
    assert decompnet.UPSTREAM_URL == UPSTREAM
    assert UPSTREAM in read("pyproject.toml") and UPSTREAM in read("README.md")
    for path in tool.files():
        text = path.read_text(encoding="utf-8")
        assert "i12bp8/Function_2_C_Decompiler" not in text, f"{path.relative_to(ROOT)}: an upstream URL was rewritten"
        assert "decomp.wtf/Function_2_C_Decompiler" not in text and "Function_2_C_Decompiler.wtf" not in text


def test_the_fork_notice_says_what_this_is_a_fork_of_by_its_own_name_and_gives_the_new_name():
    notice = read("README.md").split("---")[0]
    assert f"[decomp.wtf]({UPSTREAM})" in notice and f"**{NEW}**" in notice


# ---- the demo ROMs ------------------------------------------------------------------------------------------------------------------


def test_the_demo_builders_are_not_renamed_and_no_padded_field_is_longer_than_its_width():
    """`b"...".ljust(40)` pads a credit to a 40-byte header field and does not truncate: a longer string overflows the field and corrupts
    the executable. The tool leaves `projects/` alone, and this keeps anyone (or any tool) from making a literal too long for its slot."""
    for build in sorted((ROOT / "projects").glob("*/build.py")):
        text = build.read_text(encoding="utf-8")
        for literal, width in re.findall(r'b"([^"]*)"\.ljust\((\d+)', text):
            assert len(literal.encode()) <= int(width), f"{build.parent.name}: {literal!r} does not fit {width} bytes"
    assert "made for decomp.wtf" in read("projects/demo-psx/build.py")  # the committed demo ROM was built with this credit
