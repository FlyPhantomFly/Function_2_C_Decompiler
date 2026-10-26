"""The two small tools a release depends on: the wheel checker and the release-notes extractor.

The wheel checker is only worth having if it rejects bad wheels, so every test here starts from a known-good fake wheel and removes or adds one thing.
Package data that sits outside the package is the classic way to ship a wheel that installs fine and then has no GUI; that is the first test.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "maintenance" / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_wheel, release_notes = _load("check_wheel"), _load("release_notes")
V = "9.8.7"


def good_files() -> dict[str, str]:
    files = {n: "x" for n in check_wheel.REQUIRED}
    files |= {f"decompnet/app/guide/g{i}.md": "guide" for i in range(21)}
    files |= {f"decompnet-{V}.dist-info/METADATA": f"Metadata-Version: 2.4\nName: decompnet\nVersion: {V}\n",
              f"decompnet-{V}.dist-info/entry_points.txt": f"[console_scripts]\n{check_wheel.ENTRY_POINT}\n",
              f"decompnet-{V}.dist-info/licenses/LICENSE": "MIT", f"decompnet-{V}.dist-info/WHEEL": "Wheel-Version: 1.0\n"}
    return files


def wheel(tmp_path: Path, files: dict[str, str], name: str = "w.whl") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as z:
        for n, content in files.items():
            z.writestr(n, content)
    return path


# ---- the wheel checker ------------------------------------------------------------------------------------------------------------------------------


def test_a_complete_wheel_passes(tmp_path):
    assert check_wheel.problems(wheel(tmp_path, good_files()), V) == []


@pytest.mark.parametrize("missing", ["decompnet/app/static/index.html", "decompnet/toolchains.toml", "decompnet/app/static/demo/demo-quest-64.z64",
                                     "decompnet/forks/ghidra_scripts/DecompWtfExport.java"])
def test_a_wheel_missing_data_the_app_cannot_run_without_is_rejected_by_name(tmp_path, missing):
    files = good_files()
    del files[missing]
    assert check_wheel.problems(wheel(tmp_path, files), V) == [f"missing: {missing}"]


def test_a_wheel_that_lost_most_of_the_agents_guides_is_rejected(tmp_path):
    files = {k: v for k, v in good_files().items() if not k.startswith("decompnet/app/guide/") or int(re.search(r"/g(\d+)\.md$", k).group(1)) < 3}
    assert any("only 3 agent guides" in p for p in check_wheel.problems(wheel(tmp_path, files), V))


@pytest.mark.parametrize("stray", ["tests/test_x.py", "maintenance/CHANGELOG.md", "projects/demo/build.py", "site/public/install.sh", ".github/workflows/ci.yml",
                                   "decompnet/__pycache__/x.cpython-312.pyc", "decompnet/decomp.db.bak-v0", "decompnet/backup.sqlite", "settings.json", ".env"])
def test_a_wheel_that_ships_files_it_must_not_is_rejected(tmp_path, stray):
    files = good_files() | {stray: "x"}
    assert check_wheel.problems(wheel(tmp_path, files), V) == [f"should not ship: {stray}"]


def test_the_wheel_must_be_the_version_asked_for_and_the_right_package(tmp_path):
    assert check_wheel.problems(wheel(tmp_path, good_files()), "1.2.3") == ["the wheel's version is not 1.2.3"]
    files = good_files()
    files[f"decompnet-{V}.dist-info/METADATA"] = f"Name: something-else\nVersion: {V}\n"
    assert check_wheel.problems(wheel(tmp_path, files), V) == ["the package name is not decompnet"]


def test_the_command_and_the_license_must_be_declared(tmp_path):
    files = good_files()
    files[f"decompnet-{V}.dist-info/entry_points.txt"] = "[console_scripts]\nother = x:y\n"
    del files[f"decompnet-{V}.dist-info/licenses/LICENSE"]
    out = check_wheel.problems(wheel(tmp_path, files), V)
    assert any("`decomp` command" in p for p in out) and any("LICENSE" in p for p in out)


def test_something_that_is_not_a_wheel_is_reported_not_raised(tmp_path):
    junk = tmp_path / "junk.whl"
    junk.write_bytes(b"not a zip")
    assert "cannot be read as a wheel" in check_wheel.problems(junk, V)[0]


def test_the_command_line_exits_1_with_one_line_per_problem_and_0_when_clean(tmp_path, capsys):
    files = good_files()
    del files["decompnet/app/static/app.js"]
    assert check_wheel.main([str(wheel(tmp_path, files)), "--version", V]) == 1
    assert capsys.readouterr().out.strip().splitlines() == ["w.whl: missing: decompnet/app/static/app.js"]
    assert check_wheel.main([str(wheel(tmp_path, good_files(), "ok.whl")), "--version", V]) == 0
    assert "ok.whl: OK" in capsys.readouterr().out
    assert check_wheel.main([]) == 2


@pytest.mark.skipif(not shutil.which("uv") or not os.environ.get("BUILD_WHEEL"), reason="builds the real wheel: set BUILD_WHEEL=1 (needs uv and the network for the build backend)")
def test_the_real_wheel_built_from_this_tree_passes(tmp_path):
    """What a release would ship. CI runs the same two commands as a step; this is the same check for a person at a keyboard."""
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(ROOT)], check=True, capture_output=True, timeout=600)
    built = list(tmp_path.glob("*.whl"))
    assert len(built) == 1 and check_wheel.problems(built[0]) == []


# ---- the release notes ----------------------------------------------------------------------------------------------------------------------------------

LOG = """# Changelog

## [0.3.0] - 2026-03-03

**Fix.** The newest.

- one
- two

## [0.2.0] - 2026-02-02

**Docs.** The middle.

## [0.1.0] - 2026-01-01

**First.** The oldest, with nothing after it.
"""


def test_an_entry_is_everything_under_its_heading_up_to_the_next_one():
    assert release_notes.section(LOG, "0.3.0") == "**Fix.** The newest.\n\n- one\n- two\n"
    assert release_notes.section(LOG, "0.2.0") == "**Docs.** The middle.\n"
    assert release_notes.section(LOG, "0.1.0") == "**First.** The oldest, with nothing after it.\n"


def test_a_version_with_no_entry_gives_nothing_and_a_version_is_matched_exactly():
    assert release_notes.section(LOG, "9.9.9") is None
    assert release_notes.section(LOG, "0.3") is None and release_notes.section(LOG, "0.3.0.1") is None
    assert release_notes.section("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-12-31\ntext\n", "1.0.0") is None  # a heading with an empty body is not notes


def test_the_command_prints_the_entry_and_exits_2_with_nothing_on_stdout_when_there_is_none(tmp_path, capsys):
    log = tmp_path / "CHANGELOG.md"
    log.write_text(LOG, encoding="utf-8")
    assert release_notes.main(["0.2.0", "--changelog", str(log)]) == 0
    assert capsys.readouterr().out == "**Docs.** The middle.\n"
    assert release_notes.main(["7.7.7", "--changelog", str(log)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "no changelog entry for 7.7.7" in captured.err


def test_the_real_changelog_has_notes_for_the_version_being_released():
    import tomllib

    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    notes = release_notes.section((ROOT / "maintenance" / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    assert notes and len(notes) > 100


# ---- a release can have a name -------------------------------------------------------------------------------------------------------------------------

NAMED = """# Changelog

## [1.0.0] - 2026-05-05 - ROMday

**First.** The first release.

## [0.9.0] - 2026-04-04

**Before.** No name.
"""


def test_a_release_may_carry_a_name_after_its_date_and_the_notes_do_not_include_the_heading():
    assert release_notes.release_name(NAMED, "1.0.0") == "ROMday"
    assert release_notes.release_name(NAMED, "0.9.0") is None
    assert release_notes.release_name(NAMED, "7.7.7") is None
    assert release_notes.section(NAMED, "1.0.0") == "**First.** The first release.\n"  # the heading, and so the name, is not part of the notes


def test_the_release_title_is_the_product_the_version_and_the_name_if_there_is_one():
    assert release_notes.title(NAMED, "1.0.0") == "Function_2_C_Decompiler 1.0.0 - ROMday"
    assert release_notes.title(NAMED, "0.9.0") == "Function_2_C_Decompiler 0.9.0"
    import decompnet

    assert release_notes.PRODUCT == decompnet.PRODUCT


def test_the_title_option_prints_it_and_a_missing_entry_prints_nothing(tmp_path, capsys):
    log = tmp_path / "CHANGELOG.md"
    log.write_text(NAMED, encoding="utf-8")
    assert release_notes.main(["1.0.0", "--title", "--changelog", str(log)]) == 0
    assert capsys.readouterr().out == "Function_2_C_Decompiler 1.0.0 - ROMday\n"
    assert release_notes.main(["7.7.7", "--title", "--changelog", str(log)]) == 2
    assert capsys.readouterr().out == ""


def test_a_name_with_a_quote_or_a_shell_character_is_not_expanded_by_anything_that_reads_the_title_file(tmp_path):
    """The title travels through a file and `$(cat ...)` in the publishing job; the name comes from the changelog, which maintainers write, but the point of
    that job is that it expands nothing. A name is kept to ordinary words so there is nothing to expand in the first place."""
    for bad in ('Evil"; rm -rf ~; "', "a $(whoami) b", "back`tick`", "x" * 41, "-starts-with-a-dash"):
        log = f"## [1.0.0] - 2026-05-05 - {bad}\n\nnotes\n"
        assert release_notes.release_name(log, "1.0.0") is None, bad


def test_the_first_release_is_called_romday():
    log = (ROOT / "maintenance" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert release_notes.release_name(log, "0.11.0") == "ROMday"
    assert release_notes.title(log, "0.11.0") == "Function_2_C_Decompiler 0.11.0 - ROMday"
