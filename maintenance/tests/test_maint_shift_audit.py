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

from decompnet.rom import shiftaudit
from decompnet.app import cli

ROOT = Path(__file__).resolve().parents[2]

# Function A is 10 instructions at 0x80000460..0x80000487, function B starts at 0x80000488. Worked out by hand, so the tests can say exact numbers:
#   code:  1 symbolic lui, 1 hardcoded lui (0x8001: address-like), 1 float lui (0x3F80: ignored), 1 symbolic jal, 1 hardcoded jal, 1 symbolic j, 1 hardcoded j
#   data:  2 symbolic words, 6 absolute address words, 1 expression, and 2 small constants that are not counted
FUNC_A = """.include "macro.inc"
.section .text, "ax"

glabel func_80000460
    /* 1060 80000460 3C048000 */  lui        $a0, %hi(D_800082B0)
    /* 1064 80000464 24840000 */  addiu      $a0, $a0, %lo(D_800082B0)
    /* 1068 80000468 3C018001 */  lui        $at, 0x8001
    /* 106C 8000046C 3C013F80 */  lui        $at, 0x3F80
    /* 1070 80000470 0C000000 */  jal        func_80000488
    /* 1074 80000474 00000000 */  nop
    /* 1078 80000478 0C0000A2 */  jal        0x80000488
    /* 107C 8000047C 08000000 */  j          .L80000484
    /* 1080 80000480 08000121 */  j          0x80000484
.L80000484:
    /* 1084 80000484 03E00008 */  jr         $ra
"""
FUNC_B = """glabel func_80000488
    /* 1088 80000488 27BDFFE8 */  addiu      $sp, $sp, -0x18
    /* 108C 8000048C 00000000 */  nop
.L80000490:
    /* 1090 80000490 00000000 */  nop
    /* 1094 80000494 03E00008 */  jr         $ra
"""
DATA = """.include "macro.inc"
.section .data, "wa"

dlabel D_800082B0
    /* 8EB0 800082B0 27BD0018 */ .word 0x27BD0018
    /* 8EB4 800082B4 00000010 */ .word 0x00000010

dlabel jtbl_800082C0
    /* 8EC0 800082C0 80000484 */ .word 0x80000484
    /* 8EC4 800082C4 80000490 */ .word 0x80000490
    /* 8EC8 800082C8 8000046C */ .word 0x8000046C
    /* 8ECC 800082CC 80000460 */ .word func_80000460
    /* 8ED0 800082D0 80000490 */ .word .L80000490
    /* 8ED4 800082D4 80000488 */ .word 0x80000488
    /* 8ED8 800082D8 800082B4 */ .word 0x800082B4
    /* 8EDC 800082DC 806567CB */ .word 0x806567CB
    /* 8EE0 800082E0 80000484 */ .word 0x80000484 + 4
"""


def tree(tmp_path: Path, functions=None, data=DATA, platform="n64") -> Path:
    functions = functions if functions is not None else {"func_80000460": (0x80000460, FUNC_A), "func_80000488": (0x80000488, FUNC_B)}
    root = tmp_path / "source"
    (root / "asm" / "nonmatchings" / "main").mkdir(parents=True)
    (root / "asm" / "data").mkdir(parents=True)
    entries = []
    for name, (vram, text) in functions.items():
        (root / "asm" / "nonmatchings" / "main" / f"{name}.s").write_text(text, encoding="utf-8")
        entries.append({"name": name, "seg": "main", "vram": vram, "rom": vram - 0x80000000 + 0x1000, "asm": f"asm/nonmatchings/main/{name}.s"})
    (root / "asm" / "data" / "8EB0.data.s").write_text(data, encoding="utf-8")
    segments = [{"name": "header", "kind": "raw", "start": 0, "objects": ["build/asm/header.o"]},
                {"name": "main", "kind": "code", "start": 0x1060, "end": 0x1060 + 0x8000, "vram": 0x80000460, "bss_vram": 0x80008460, "bss_size": 0x1000,
                 "pieces": [{"vram": 0x800082B0, "obj": "build/asm/data/8EB0.data.o"}], "bss": []},
                {"name": "tail", "kind": "raw", "start": 0x9060, "objects": ["build/asm/bin/tail.o"]}]
    (root / "build.json").write_text(json.dumps({"platform": platform, "functions": entries, "segments": segments, "symbols": {}, "image": "baserom.z64"}), encoding="utf-8")
    return root


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
    assert data["symbolic_words"] == 2  # func_80000460 and .L80000488
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
    assert data["absolute_words"] + data["symbolic_words"] + data["other_expressions"] == 9  # 0x27BD0018 and 0x00000010 are neither


def test_a_jump_table_entry_says_whether_the_functions_assembly_already_has_a_label_at_its_target(tmp_path):
    report = shiftaudit.audit(tree(tmp_path))
    found = {f["value"]: f["label_at_target"] for f in report["findings"] if f["kind"] == "jump-table entry"}
    assert found == {0x80000484: True, 0x80000490: True, 0x8000046C: False}  # `.L80000484:` is in A, `.L80000490:` in B, and nothing labels 0x8000046C
    assert report["data"]["jump_table_entries_without_a_label"] == 1


def test_a_tree_with_only_symbols_is_shiftable_and_one_with_numbers_says_what_blocks_it(tmp_path):
    clean = shiftaudit.audit(tree(tmp_path / "a", {"func_80000460": (0x80000460, "glabel func_80000460\n    /* 1 80000460 0 */  jal        func_80000480\n")}, data="dlabel D_1\n    /* 1 800082B0 0 */ .word func_80000460\n"))
    assert clean["verdict"]["shiftable_as_exported"] is True and clean["verdict"]["blockers"] == []
    dirty = shiftaudit.audit(tree(tmp_path / "b"))
    assert dirty["verdict"]["shiftable_as_exported"] is False
    assert any("5 words" in b and "absolute addresses" in b for b in dirty["verdict"]["blockers"])  # 5, not 6: the one outside the program is a constant and does not block
    assert any("lui" in b for b in dirty["verdict"]["blockers"]) and any("jal" in b or "jump" in b for b in dirty["verdict"]["blockers"])


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
    assert cli.main(["shift-audit", str(root), "--strict"]) == 1
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
    assert report["verdict"]["shiftable_as_exported"] is False
    jt = next(f for f in report["findings"] if f["value"] == 0x80000958)
    assert jt["target"].startswith("func_8000092C+0x") and jt["label_at_target"] is False


@needs_demo
def test_the_command_on_the_real_demo_export(demo_tree, capsys):
    assert cli.main(["shift-audit", str(demo_tree)]) == 0
    out = capsys.readouterr().out
    assert "96 functions" in out and "39 jump-table entries (38 with no label at the target)" in out and "Verdict: NOT shiftable as exported" in out
