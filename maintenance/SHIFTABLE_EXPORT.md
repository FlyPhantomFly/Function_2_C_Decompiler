# The N64 shiftable export: what it needs, what was measured, how it will be verified

Status: **step 1 of 6 done: the audit exists** (`decomp shift-audit`, 0.11.1). Nothing that changes a build is implemented. Everything under "measured" was counted on the exported demo ROM (Demo Quest 64, 96 functions); the audit now reproduces the numbers by itself.

## What "shiftable" means here

Today the export rebuilds the game byte for byte because **every function and data block is pinned to its original address**. A mod that makes code bigger cannot be built, because the layout will not move. A shiftable build lets
code grow: later code, and the data after it, move, and everything that refers to them still lands on the right place.

## What pins the layout today (read from `build.py`, which the export writes)

- **Functions:** `linker_script()` writes `. = 0x<offset>; <object>(.text)` for each one, so each sits at its original offset.
- **Named data symbols:** defined as absolute numbers (`name = 0x80008928;`) from `build.json`.
- **Jump-table labels:** pinned the same way (`".L80008998" = 0x80008998;`).
- **Segment symbols:** `<seg>_ROM_START`, `<seg>_VRAM_END`, `<seg>_BSS_END` and the like are constants.
- (The export also carries splat's own linker script, which does flow. `build.py` does not use it for the build.)

## Measured on the demo export

| | |
|---|---|
| Code references that are symbolic: `lui ... %hi(symbol)` | 138 |
| Calls that are symbolic (`jal symbol`) | 147 |
| Code references that are absolute numbers (`lui` with a number, `jal`/`j` to a number) | **0** |
| Words in data that are symbols/labels | 26 |
| Words in data that are absolute RAM addresses | **40** (39 are jump-table entries: addresses *inside* functions, written as numbers; 1 is a constant that is not an address). **38 of the 39 have no label at their target**: the disassembler never emitted one. The 39th (`0x80003A24`, in `func_8000321C`) happens to be a branch target too, so it already has one |
| Named symbols pinned as absolute numbers | 1 |
| Segments | `header`, `ipl3` (raw), `entry` and `main` (code), one more raw block |

So in the demo the *code* is already relocatable, and what is not is the **jump tables**: if code before them grows, a table of raw addresses jumps to the wrong place. That is the first thing a shiftable build must fix, and it is the
thing most likely to be wrong in a real game too (switch statements are everywhere).

## What a shiftable layout needs

1. A second layout mode in the generated `build.py`: functions placed one after another in their original order (no `. = offset`), data after the code as before, segment start addresses kept and later ones flowing from the previous end.
2. Data symbols defined by where their data object lands, not as absolute numbers.
3. **Jump-table entries turned into symbolic references** to labels inside the function objects, which need stable global names. Since 38 of the demo's 39 targets have no label, this step must **insert** a label at each target in the function's assembly (an instruction boundary the table already points at), and then export it.
4. The segment-end symbols computed by the linker.
5. **The ROM header checksums recomputed** after the link (any change to the first megabyte invalidates them, and real hardware and some emulators check them). The algorithm is already written and checked: with the standard routine and the CIC 6102 seed,
   the demo ROM's stored header checksums (`6c8d30eb 81ee9bcf`) are reproduced exactly. Other boot chips use other seeds; they are not verified here.
6. The build must stop treating "not identical to the original" as failure when the tree has been modified on purpose: it reports what moved.

## How it will be verified (in this order, each step before the next)

1. **An audit** (read-only): classify every absolute-looking word in data and every absolute number in code as symbolic, jump-table, or a constant, and say which ones a shift would break. **Done (0.11.1): `decomp shift-audit PROJECT`** (`--json`, `--strict`). It also says what it does not look at: overlays, compressed segments, ROM offsets kept in the game, addresses built by arithmetic, the header checksums, and what refers to a raw segment after the code.
2. **No-change test:** the shiftable build of an *unmodified* tree is byte-identical to the original. This proves the transformation (3 above) changed nothing by itself.
3. **Growth test:** insert code at the start of the main segment and rebuild. Check that it links, that the checksums are valid, and that a normalized comparison holds: every function, with its calls, data references and jump-table
   entries mapped through the old-to-new addresses, equals the original. A reference the build failed to relocate shows up as a mismatch.
4. **Execution test** where possible: run functions in a MIPS emulator (Unicorn) before and after the shift and compare results. Not available in this project's dependencies, so a test that needs it would skip without it.

## Out of scope for a first version (and the docs must say so)

Overlays and code loaded later, compressed segments, ROM-offset tables and DMA tables inside the game (code growing moves what they point at), code that builds addresses arithmetically, and boot chips other than 6102 until they are checked. Real
games (Super Mario 64, GoldenEye, Perfect Dark, the ones the README says are tested) have all of these; **a version that grows the main program's code in a demo-class ROM would be honest to ship, but must not be described as working on those games.**
