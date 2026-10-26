"""`rom/luvdis_run.py` fixes a bug in the GBA disassembler by rewriting a piece of its source before running it.

That only works for the luvdis it was written for. If the text it patches is not there exactly once (a different luvdis, or
one that fixed the bug itself), the old code did nothing and went on with the unpatched program, so the crash it exists to
prevent came back without a word. These tests pin: the patch applies to the pinned luvdis exactly once; a different luvdis is
refused with a message that says why and what to update; and the replacement code means what the docstring says.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

from decompnet import toolchains
from decompnet.rom import luvdis_run

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(luvdis_run.__file__)
luvdis_dir = toolchains.path("luvdis")
needs_luvdis = pytest.mark.skipif(toolchains.installed("luvdis") is None, reason="needs luvdis (`decomp toolchain install luvdis`)")


def _analyze_source() -> tuple[Path, str]:
    path = next(luvdis_dir.rglob("luvdis/analyze.py"))
    return path, path.read_text(encoding="utf-8")


def _push(code: str):
    """The fixed (or original) push, as a function: the snippet sits deep inside luvdis's method, so dedent it."""
    source = "def push(self, value):\n" + textwrap.indent(textwrap.dedent(code), "    ")
    scope: dict = {}
    exec(source, scope)
    return scope["push"]


class Machine:
    def __init__(self, stack, sp):
        self.stack, self.sp = list(stack), sp


def test_luvdis_is_pinned_to_one_full_commit():
    entry = tomllib.loads((ROOT / "src" / "decompnet" / "toolchains.toml").read_text(encoding="utf-8"))["luvdis"]
    assert len(entry["commit"]) == 40 and set(entry["commit"]) <= set("0123456789abcdef")


@needs_luvdis
def test_the_fix_applies_to_the_pinned_luvdis_exactly_once():
    _, source = _analyze_source()
    assert source.count(luvdis_run.PUSH) == 1
    fixed = luvdis_run.patched(source)
    assert luvdis_run.SAFE_PUSH in fixed and luvdis_run.PUSH not in fixed
    compile(fixed, "luvdis/analyze.py", "exec")


@pytest.mark.parametrize("what, source, count", [
    ("a luvdis without the code", "class A:\n    pass\n", 0),
    ("a luvdis that fixed the bug itself", luvdis_run.SAFE_PUSH, 0),
    ("code that appears twice", luvdis_run.PUSH + "\n" + luvdis_run.PUSH, 2),
])
def test_a_luvdis_it_was_not_written_for_is_refused_with_a_message_that_says_why(what, source, count):
    with pytest.raises(SystemExit) as stop:
        luvdis_run.patched(source)
    message = str(stop.value)
    assert f"found it {count} times" in message, what
    assert "toolchains.toml" in message and "update luvdis_run.py" in message


def test_running_against_a_different_luvdis_stops_instead_of_going_on_unpatched(tmp_path):
    package = tmp_path / "luvdis"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "analyze.py").write_text("x = 1\n", encoding="utf-8")
    (package / "__main__.py").write_text("def main(prog_name):\n    print('LUVDIS RAN')\n    return 0\n", encoding="utf-8")
    done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60,
                          env={"PYTHONPATH": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert done.returncode != 0
    assert "found it 0 times" in done.stderr
    assert "LUVDIS RAN" not in done.stdout  # it did not run luvdis anyway


@needs_luvdis
def test_the_patched_luvdis_starts_from_the_script_in_its_own_environment():
    python = toolchains.venv_bin(luvdis_dir / "venv", "python")
    done = subprocess.run([str(python), "-I", str(SCRIPT), "--help"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert "disasm" in done.stdout


# ---- what the replacement code means ---------------------------------------------------------------------------------


@pytest.mark.parametrize("sp", [-1, -2, -5, -100])
def test_a_push_below_the_start_of_the_stack_stores_nothing(sp):
    machine = Machine([10, 20], sp)
    _push(luvdis_run.SAFE_PUSH)(machine, 99)
    assert machine.stack == [10, 20]


def test_the_original_code_corrupted_the_stack_for_minus_one_and_crashed_below_it():
    """Why the fix is a correctness fix and not just a crash fix: sp == -1 wrote over the last word silently."""
    push = _push(luvdis_run.PUSH)
    silently_wrong = Machine([10, 20], -1)
    push(silently_wrong, 99)
    assert silently_wrong.stack == [10, 99]
    with pytest.raises(IndexError):
        push(Machine([10, 20], -3), 99)


@pytest.mark.parametrize("sp, expected", [(0, [99, 20]), (1, [10, 99]), (2, [10, 20, 99]), (7, [10, 20, 99])])
def test_a_normal_push_behaves_exactly_as_before(sp, expected):
    for code in (luvdis_run.PUSH, luvdis_run.SAFE_PUSH):
        machine = Machine([10, 20], sp)
        _push(code)(machine, 99)
        assert machine.stack == expected
