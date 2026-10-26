"""A small synthetic N64 export tree, shared by the shift-audit and shift-prep tests. Not a test module."""

from __future__ import annotations

import json
from pathlib import Path

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
