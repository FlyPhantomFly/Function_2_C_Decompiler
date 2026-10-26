"""`decomp shift-prep`: make an exported N64 tree's references symbolic, without changing what it builds. Step two of the shiftable export.

For every jump-table entry (and every `.word .L<address>`, which the generated linker script pins to a number) it inserts a global label at the target in the function's assembly and
rewrites the entry to use it; a word that is the exact start of a function becomes that function's name. Nothing about the layout changes, so the ROM must still rebuild byte for byte:
that is the test that matters, and it runs on the real demo through the tree's own build.py. It previews by default, changes only what it can prove it understands, and writes a manifest.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from shift_fixture import DATA, FUNC_A, FUNC_B, tree

from decompnet.app import cli
from decompnet.rom import shiftaudit, shiftprep, split

ROOT = Path(__file__).resolve().parents[2]


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def a_asm(root: Path) -> str:
    return (root / "asm/nonmatchings/main/func_80000460.s").read_text(encoding="utf-8")


# ---- previewing ------------------------------------------------------------------------------------------------------------------------------------------


def test_the_default_is_a_preview_that_changes_nothing_and_says_exactly_what_it_would_do(tmp_path):
    root = tree(tmp_path)
    before = snapshot(root)
    plan = shiftprep.prepare(root)  # apply=False
    assert snapshot(root) == before
    assert (plan["applied"], len(plan["labels"]), len(plan["words"])) == (False, 3, 5)
    assert sorted(l["address"] for l in plan["labels"]) == [0x8000046C, 0x80000484, 0x80000490]
    assert sorted(w["line"] for w in plan["words"]) == [9, 10, 11, 13, 14]


# ---- applying ---------------------------------------------------------------------------------------------------------------------------------------------


def test_a_label_is_inserted_at_each_target_just_before_its_instruction_and_after_any_label_already_there(tmp_path):
    root = tree(tmp_path)
    shiftprep.prepare(root, apply=True)
    a = a_asm(root)
    assert ".globl jtgt_8000046C\njtgt_8000046C:\n    /* 106C 8000046C 3C013F80 */  lui" in a  # a target with no label: inserted right before its instruction
    assert ".L80000484:\n.globl jtgt_80000484\njtgt_80000484:\n    /* 1084 80000484 03E00008 */  jr" in a  # one that has a local label: ours goes after it, at the same address
    b = (root / "asm/nonmatchings/main/func_80000488.s").read_text(encoding="utf-8")
    assert ".L80000490:\n.globl jtgt_80000490\njtgt_80000490:\n    /* 1090 80000490 00000000 */  nop" in b
    assert a.count("jtgt_") == 2 * 2 and b.count("jtgt_") == 1 * 2  # A gets two labels, B one; each is a .globl line and a label line


def test_the_table_entries_are_rewritten_and_only_those_the_rest_of_the_line_is_untouched(tmp_path):
    root = tree(tmp_path)
    shiftprep.prepare(root, apply=True)
    lines = (root / "asm/data/8EB0.data.s").read_text(encoding="utf-8").splitlines()
    assert lines[8] == "    /* 8EC0 800082C0 80000484 */ .word jtgt_80000484"
    assert lines[9] == "    /* 8EC4 800082C4 80000490 */ .word jtgt_80000490"
    assert lines[10] == "    /* 8EC8 800082C8 8000046C */ .word jtgt_8000046C"
    assert lines[12] == "    /* 8ED0 800082D0 80000490 */ .word jtgt_80000490"  # `.word .L80000490`: a local label pinned by the build, now a real symbol
    assert lines[13] == "    /* 8ED4 800082D4 80000488 */ .word func_80000488"  # the exact start of a function: its name
    assert lines[11].endswith(".word func_80000460")  # already a symbol: untouched
    assert lines[14].endswith(".word 0x800082B4") and lines[15].endswith(".word 0x806567CB") and lines[16].endswith(".word 0x80000484 + 4")  # not supported yet / not an address / not understood: left alone


def test_afterwards_the_audit_finds_the_references_it_could_fix_gone_and_the_rest_still_reported(tmp_path):
    root = tree(tmp_path)
    shiftprep.prepare(root, apply=True)
    data = shiftaudit.audit(root)["data"]
    assert data["kinds"] == {"data pointer": 1, "outside the image": 1} and data["pinned_labels"] == 0 and data["jump_table_entries_without_a_label"] == 0
    assert data["symbolic_words"] == 6  # func_80000460 and the five that were rewritten
    assert shiftaudit.audit(root)["verdict"]["references_ready"] is False  # the data pointer is not handled yet, and the audit still says so


def test_running_it_again_changes_nothing(tmp_path):
    root = tree(tmp_path)
    shiftprep.prepare(root, apply=True)
    once = snapshot(root)
    again = shiftprep.prepare(root, apply=True)
    assert snapshot(root) == once and (len(again["labels"]), len(again["words"])) == (0, 0)


def test_the_matchers_view_of_a_function_is_the_same_before_and_after(tmp_path):
    """split.parse_function (what `build.py check` matches against) ignores lines it does not know: this proves it, for the lines this step adds."""
    root = tree(tmp_path)
    path = root / "asm/nonmatchings/main/func_80000460.s"
    before = split.parse_function(path, "main")
    shiftprep.prepare(root, apply=True)
    after = split.parse_function(path, "main")
    assert [(l.rom, l.vram, l.word, l.mnemonic, l.operands) for l in after.lines] == [(l.rom, l.vram, l.word, l.mnemonic, l.operands) for l in before.lines]
    assert after.labels == before.labels and after.name == before.name


# ---- what it leaves alone, and says so -----------------------------------------------------------------------------------------------------------------------


def test_a_target_with_no_instruction_line_to_put_a_label_before_is_left_alone_and_reported(tmp_path):
    no_470 = "\n".join(line for line in FUNC_A.splitlines() if "80000470" not in line) + "\n"
    data = DATA + "    /* 8EE4 800082E4 80000470 */ .word 0x80000470\n"
    root = tree(tmp_path, {"func_80000460": (0x80000460, no_470), "func_80000488": (0x80000488, FUNC_B)}, data=data)
    plan = shiftprep.prepare(root, apply=True)
    assert any(w["value"] == 0x80000470 and "no instruction" in w["reason"] for w in plan["left_alone"])
    assert (root / "asm/data/8EB0.data.s").read_text(encoding="utf-8").rstrip().endswith(".word 0x80000470")  # not rewritten to a label that does not exist


def test_a_label_of_that_name_that_is_already_there_is_reused_not_duplicated(tmp_path):
    with_label = FUNC_A.replace("    /* 1084 80000484 03E00008 */", ".globl jtgt_80000484\njtgt_80000484:\n    /* 1084 80000484 03E00008 */")
    root = tree(tmp_path, {"func_80000460": (0x80000460, with_label), "func_80000488": (0x80000488, FUNC_B)})
    plan = shiftprep.prepare(root, apply=True)
    assert a_asm(root).count("jtgt_80000484:") == 1 and 0x80000484 not in [l["address"] for l in plan["labels"]]
    assert (root / "asm/data/8EB0.data.s").read_text(encoding="utf-8").splitlines()[8].endswith(".word jtgt_80000484")


def test_the_manifest_records_every_change_so_it_can_be_reviewed_or_undone_by_hand(tmp_path):
    root = tree(tmp_path)
    shiftprep.prepare(root, apply=True)
    manifest = json.loads((root / "shift-prep.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 1 and len(manifest["labels"]) == 3 and len(manifest["words"]) == 5
    word = next(w for w in manifest["words"] if w["line"] == 9)
    assert (word["file"], word["was"], word["now"]) == ("asm/data/8EB0.data.s", "0x80000484", "jtgt_80000484")
    label = next(l for l in manifest["labels"] if l["address"] == 0x80000484)
    assert (label["function"], label["name"], label["file"]) == ("func_80000460", "jtgt_80000484", "asm/nonmatchings/main/func_80000460.s")


def test_a_folder_that_is_not_an_export_is_refused(tmp_path):
    with pytest.raises(shiftaudit.AuditError, match="no build.json"):
        shiftprep.prepare(tmp_path)


# ---- the command ------------------------------------------------------------------------------------------------------------------------------------------


def test_the_command_previews_applies_and_reports_nothing_to_do_the_second_time(tmp_path, capsys):
    root = tree(tmp_path)
    before = snapshot(root)
    assert cli.main(["shift-prep", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Would insert 3 labels and rewrite 5 words" in out and "--apply" in out and snapshot(root) == before
    assert cli.main(["shift-prep", str(root), "--apply"]) == 0
    assert "Inserted 3 labels and rewrote 5 words" in capsys.readouterr().out
    assert cli.main(["shift-prep", str(root), "--apply"]) == 0
    assert "Nothing to do" in capsys.readouterr().out
    assert cli.main(["shift-prep", str(tmp_path / "nowhere")]) == 1
    assert capsys.readouterr().err.startswith("error: ")


# ---- the real thing ------------------------------------------------------------------------------------------------------------------------------------------


def _problem() -> str:
    sys.path.insert(0, str(ROOT / "maintenance" / "tools"))
    import eval_agent

    return eval_agent.problem()


needs_demo = pytest.mark.skipif(bool(_problem()), reason=_problem() or "")


@pytest.fixture
def demo_tree(tmp_path):
    from decompnet.app.engine import RomNetwork

    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    slug = net.import_rom((ROOT / "src" / "decompnet" / "app" / "static" / "demo" / "demo-quest-64.z64").read_bytes(), confirmed=True, name="demo-quest-64.z64", log=lambda *_: None)
    net.export_rom(slug, log=lambda *_: None)
    return home / slug / "source"


def build(root: Path) -> tuple[int, str]:
    done = subprocess.run([sys.executable, "build.py"], cwd=root, capture_output=True, text=True, timeout=600)
    return done.returncode, (done.stdout + done.stderr).strip().splitlines()[-1]


@needs_demo
def test_on_the_real_demo_the_tree_rebuilds_byte_for_byte_before_and_after(demo_tree):
    """The point of this step: the references become symbols and the ROM does not change at all."""
    code, line = build(demo_tree)
    assert code == 0 and line.startswith("identical: "), line
    plan = shiftprep.prepare(demo_tree, apply=True)
    assert len(plan["labels"]) == 39 and len(plan["words"]) == 39
    code, line = build(demo_tree)
    assert code == 0 and line.startswith("identical: "), line  # 39 labels inserted, 39 table entries rewritten, and the ROM is the same bytes


@needs_demo
def test_on_the_real_demo_the_audit_then_has_nothing_left_to_block_it(demo_tree):
    shiftprep.prepare(demo_tree, apply=True)
    report = shiftaudit.audit(demo_tree)
    assert report["data"]["kinds"] == {"outside the image": 1} and report["data"]["symbolic_words"] == 26 + 39
    assert report["verdict"]["references_ready"] is True and report["verdict"]["blockers"] == []
    assert report["verdict"]["shiftable_as_exported"] is False  # the references are ready; the generated build still pins the layout, and the audit says so


@needs_demo
def test_on_the_real_demo_functions_can_still_be_matched_in_c_after_the_prep(demo_tree):
    """The matcher parses the same assembly this step adds lines to, and ignores lines it does not know: this is the proof that nothing it needs was disturbed.
    Two known-correct functions (one touches data) are written in C, matched with the tree's own `build.py check`, and the whole tree rebuilds identical with them in C."""
    sys.path.insert(0, str(ROOT / "maintenance" / "tools"))
    import eval_agent

    shiftprep.prepare(demo_tree, apply=True)
    src = demo_tree / "src" / "main"
    src.mkdir(parents=True, exist_ok=True)
    for name, source in (("func_800007F4", eval_agent.ABS), ("func_80000808", eval_agent.DAMAGE)):
        (src / f"{name}.c").write_text('#include "common.h"\n' + source + "\n", encoding="utf-8")
        done = subprocess.run([sys.executable, "build.py", "check", name], cwd=demo_tree, capture_output=True, text=True, timeout=600)
        assert done.returncode == 0 and "identical to the original" in done.stdout, done.stdout + done.stderr
    code, line = build(demo_tree)
    assert code == 0 and line.startswith("identical: ") and "(2 of 96 functions in C)" in line, line
