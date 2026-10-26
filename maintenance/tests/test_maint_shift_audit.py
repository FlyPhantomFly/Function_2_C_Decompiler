"""The shiftable-export audit: what in an exported N64 tree is pinned to an absolute address, so that growing code would break it.

Step one of the shiftable export (see maintenance/SHIFTABLE_EXPORT.md). It only reads a tree, and says, for every address-like value, whether the linker can already move it
(a symbol or label) or not (a number), what a number points at, and, for a jump-table entry, whether the function's assembly has a label at the target to point to instead.
The classification is tested on synthetic trees with exact counts; the real demo export is checked against the numbers measured on it by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from decompnet.app import cli
from decompnet.rom import shiftaudit
from shift_fixture import DATA, FUNC_A, FUNC_B, tree  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]

# ---- the code ---------------------------------------------------------------------------------------------------------------------------------------


def test_code_references_are_split_into_what_the_linker_can_move_and_what_it_cannot(tmp_path):
    code = shiftaudit.audit(tree(tmp_path))["code"]
    assert code["symbolic_hi"] == 1  # lui %hi(D_800082B0)
    assert code["hardcoded_hi"] == 1  # lui $at, 0x8001: looks like an address (0x8000 to 0x807F) and is a number
    assert (code["symbolic_calls"], code["hardcoded_calls"]) == (1, 1)  # jal func_80000488; jal 0x80000488
    assert (code["symbolic_jumps"], code["hardcoded_jumps"]) == (1, 1)  # j .L80000484; j 0x80000484


def test_a_float_constant_in_a_lui_and_numbers_inside_comments_are_not_mistaken_for_addresses(tmp_path):
    text = ('glabel func_80000460\n    /* 1060 80000460 3C013F80 */  lui        $at, 0x3F80\n    /* 1064 80000464 3C01A430 */  lui        $at, 0xA430\n'
            '    /* 1068 80000468 3C018000 */  lui        $at, %hi(sym)  /* 0x8000 in a comment */\n')
    code = shiftaudit.audit(tree(tmp_path, {"func_80000460": (0x80000460, text)}, data=""))["code"]
    assert (code["hardcoded_hi"], code["symbolic_hi"], code["hardcoded_jumps"]) == (0, 1, 0)


# ---- the data ---------------------------------------------------------------------------------------------------------------------------------------


def test_every_word_in_data_is_classified_and_what_each_absolute_one_points_at_is_named(tmp_path):
    report = shiftaudit.audit(tree(tmp_path))
    data = report["data"]
    assert data["symbolic_words"] == 1  # func_80000460
    assert data["pinned_labels"] == 1  # .L80000490: a local label, which the generated linker script defines as an absolute number: as pinned as a raw address
    assert data["absolute_words"] == 6 and data["kinds"] == {"jump-table entry": 3, "function pointer": 1, "data pointer": 1, "outside the image": 1}
    assert data["other_expressions"] == 1  # 0x80000484 + 4: not classified, said so
    entry = next(f for f in report["findings"] if f["value"] == 0x80000484)
    assert (entry["kind"], entry["target"], entry["file"], entry["line"]) == ("jump-table entry", "func_80000460+0x24", "asm/data/8EB0.data.s", 9)
    assert next(f for f in report["findings"] if f["value"] == 0x80000490)["target"] == "func_80000488+0x8"
    start = next(f for f in report["findings"] if f["value"] == 0x80000488)
    assert (start["kind"], start["target"]) == ("function pointer", "func_80000488")
    assert next(f for f in report["findings"] if f["value"] == 0x800082B4)["target"] == "D_800082B0+0x4"  # counted from the data label before it
    assert next(f for f in report["findings"] if f["value"] == 0x806567CB)["kind"] == "outside the image"


def test_small_numbers_are_constants_not_addresses_and_are_not_counted(tmp_path):
    data = shiftaudit.audit(tree(tmp_path))["data"]
    assert data["absolute_words"] + data["symbolic_words"] + data["pinned_labels"] + data["other_expressions"] == 9  # 0x27BD0018 and 0x00000010 are neither


def test_a_jump_table_entry_says_whether_the_functions_assembly_already_has_a_label_at_its_target(tmp_path):
    report = shiftaudit.audit(tree(tmp_path))
    found = {f["value"]: f["label_at_target"] for f in report["findings"] if f["kind"] == "jump-table entry"}
    assert found == {0x80000484: True, 0x80000490: True, 0x8000046C: False}  # `.L80000484:` is in A, `.L80000490:` in B, and nothing labels 0x8000046C
    assert report["data"]["jump_table_entries_without_a_label"] == 1


def test_a_tree_with_only_symbols_is_shiftable_and_one_with_numbers_says_what_blocks_it(tmp_path):
    clean = shiftaudit.audit(tree(tmp_path / "a", {"func_80000460": (0x80000460, "glabel func_80000460\n    /* 1 80000460 0 */  jal        func_80000480\n")}, data="dlabel D_1\n    /* 1 800082B0 0 */ .word func_80000460\n"))
    assert clean["verdict"]["references_ready"] is True and clean["verdict"]["blockers"] == []
    # ready references are not a shiftable build: the generated build still pins every function to its address, and the verdict must not say otherwise
    assert clean["verdict"]["shiftable_as_exported"] is False and clean["verdict"]["layout"] == "fixed"
    dirty = shiftaudit.audit(tree(tmp_path / "b"))
    assert dirty["verdict"]["references_ready"] is False and dirty["verdict"]["shiftable_as_exported"] is False
    assert any("5 words" in b and "absolute addresses" in b for b in dirty["verdict"]["blockers"])  # 5, not 6: the one outside the program is a constant and does not block
    assert any("lui" in b for b in dirty["verdict"]["blockers"]) and any("jal" in b or "jump" in b for b in dirty["verdict"]["blockers"])
    assert any("`.L" in b and "1 " in b for b in dirty["verdict"]["blockers"])  # the pinned local label is a blocker too


def test_the_text_never_says_shiftable_while_the_layout_is_still_fixed_even_when_every_reference_is_a_symbol(tmp_path):
    clean = shiftaudit.audit(tree(tmp_path / "a", {"func_80000460": (0x80000460, "glabel func_80000460\n    /* 1 80000460 0 */  jal        func_80000488\n")}, data="dlabel D_1\n    /* 1 800082B0 0 */ .word func_80000460\n"))
    text = shiftaudit.render(clean)
    assert "Verdict: the references are ready" in text and "still pins every function" in text and "code cannot grow yet" in text
    assert "NOT shiftable" not in text and "Verdict: shiftable" not in text


def test_a_tree_whose_build_is_marked_as_a_shifting_layout_and_has_ready_references_is_shiftable(tmp_path):
    root = tree(tmp_path, {"func_80000460": (0x80000460, "glabel func_80000460\n    /* 1 80000460 0 */  jal        func_80000488\n")}, data="dlabel D_1\n    /* 1 800082B0 0 */ .word func_80000460\n")
    build = json.loads((root / "build.json").read_text())
    build["layout"] = "shift"
    (root / "build.json").write_text(json.dumps(build))
    verdict = shiftaudit.audit(root)["verdict"]
    assert verdict["layout"] == "shift" and verdict["shiftable_as_exported"] is True
    assert "Verdict: shiftable as exported" in shiftaudit.render(shiftaudit.audit(root))


def test_what_the_audit_does_not_look_at_is_always_said(tmp_path):
    notes = " ".join(shiftaudit.audit(tree(tmp_path))["verdict"]["not_audited"])
    for word in ("overlay", "compress", "ROM offset", "tail"):  # `tail` is the raw segment after the code in this tree: its ROM position moves when code grows
        assert word in notes, word


# ---- what it refuses -----------------------------------------------------------------------------------------------------------------------------------


def test_a_folder_that_is_not_an_export_and_a_platform_it_does_not_know_are_refused_with_a_sentence(tmp_path):
    with pytest.raises(shiftaudit.AuditError, match="no build.json"):
        shiftaudit.audit(tmp_path)
    with pytest.raises(shiftaudit.AuditError, match="N64"):
        shiftaudit.audit(tree(tmp_path / "psx", platform="psx"))


def test_odd_assembly_does_not_crash_it(tmp_path):
    root = tree(tmp_path, {"func_80000460": (0x80000460, "\x00\x01 binary \xff garbage\n\n   lui\n  .word\n jal\n")}, data=".word\n.word 0xZZZ\n.word 0x80000460,0x80000464\n")
    assert shiftaudit.audit(root)["functions"] == 1


# ---- the report and the command ----------------------------------------------------------------------------------------------------------------------------


def test_the_text_report_reads_in_plain_words_with_examples_and_a_verdict(tmp_path):
    text = shiftaudit.render(shiftaudit.audit(tree(tmp_path)))
    for needle in ("Shiftable audit", "2 functions", "address loads use %hi(symbol)", "absolute RAM addresses", "jump-table entries", "asm/data/8EB0.data.s:9",
                   "func_80000460+0x24", "Verdict: NOT shiftable as exported", "Not audited"):
        assert needle in text, needle


def test_the_command_prints_the_report_json_on_request_and_strict_makes_a_blocker_an_exit_code(tmp_path, capsys):
    root = tree(tmp_path)
    assert cli.main(["shift-audit", str(root)]) == 0
    assert "Verdict: NOT shiftable" in capsys.readouterr().out
    assert cli.main(["shift-audit", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["absolute_words"] == 6
    assert cli.main(["shift-audit", str(root), "--strict"]) == 1  # references that would break
    capsys.readouterr()
    ready = tree(tmp_path / "ready", {"func_80000460": (0x80000460, "glabel func_80000460\n    /* 1 80000460 0 */  jal        func_80000488\n")}, data="dlabel D_1\n    /* 1 800082B0 0 */ .word func_80000460\n")
    assert cli.main(["shift-audit", str(ready), "--strict"]) == 0  # --strict is about references: it does not fail a tree for a layout it cannot yet change
    capsys.readouterr()
    assert cli.main(["shift-audit", str(tmp_path / "nowhere")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and "Traceback" not in err


# ---- the real thing ------------------------------------------------------------------------------------------------------------------------------------------


def _problem() -> str:
    sys.path.insert(0, str(ROOT / "maintenance" / "tools"))
    import eval_agent

    return eval_agent.problem()


needs_demo = pytest.mark.skipif(bool(_problem()), reason=_problem() or "")


@pytest.fixture(scope="module")
def demo_tree(tmp_path_factory):
    from decompnet.app.engine import RomNetwork

    home = tmp_path_factory.mktemp("demo-export")
    (home / ".decomp").mkdir()
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    slug = net.import_rom((ROOT / "src" / "decompnet" / "app" / "static" / "demo" / "demo-quest-64.z64").read_bytes(), confirmed=True, name="demo-quest-64.z64", log=lambda *_: None)
    net.export_rom(slug, log=lambda *_: None)
    return home / slug / "source"


@needs_demo
def test_on_the_real_demo_export_the_audit_finds_what_was_measured_by_hand(demo_tree):
    report = shiftaudit.audit(demo_tree)
    assert report["functions"] == 96
    code = report["code"]
    assert (code["symbolic_hi"], code["symbolic_calls"]) == (138, 147)  # as counted by hand
    assert (code["hardcoded_hi"], code["hardcoded_calls"], code["hardcoded_jumps"]) == (0, 0, 0)
    data = report["data"]
    assert data["absolute_words"] == 40 and data["kinds"]["jump-table entry"] == 39 and data["kinds"]["outside the image"] == 1 and data["symbolic_words"] == 26
    assert data["jump_table_entries_without_a_label"] == 38  # the disassembler left no label at 38 of them, so one has to be inserted at each
    labelled = [f for f in report["findings"] if f["kind"] == "jump-table entry" and f["label_at_target"]]
    assert [(f["value"], f["target"]) for f in labelled] == [(0x80003A24, "func_8000321C+0x808")]  # the one target that is also a branch target, and so has a label already
    assert report["verdict"]["shiftable_as_exported"] is False and report["verdict"]["references_ready"] is False
    jt = next(f for f in report["findings"] if f["value"] == 0x80000958)
    assert jt["target"].startswith("func_8000092C+0x") and jt["label_at_target"] is False


@needs_demo
def test_the_command_on_the_real_demo_export(demo_tree, capsys):
    assert cli.main(["shift-audit", str(demo_tree)]) == 0
    out = capsys.readouterr().out
    assert "96 functions" in out and "39 jump-table entries (38 with no label at the target)" in out and "Verdict: NOT shiftable as exported" in out
