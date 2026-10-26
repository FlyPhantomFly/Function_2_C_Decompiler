# The N64 shiftable export: what it needs, what was measured, how it will be verified

Status: **steps 1 to 5 of 6 done for a demo-class ROM: the audit, the symbolic references, the shifting layout, the checksum fix and the growth test** (`decomp shift-audit` 0.11.1, `decomp shift-prep` 0.11.2, `decomp shift-prep --layout` 0.11.3). **Verified on the demo ROM only.** Nothing here has been run on a real game, and the limits below are real limits. Everything under "measured" was counted on the exported demo ROM (Demo Quest 64, 96 functions); the audit now reproduces the numbers by itself.

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
2. **No-change test:** the transformation of the references (3 above) must change nothing by itself. **Done (0.11.2): `decomp shift-prep`.** On the demo it inserts 39 labels and rewrites 39 jump-table entries, and the tree's own `build.py` still says `identical` (byte for byte), before and after; two functions can then still be matched in C and the whole tree still rebuilds identical. It is explicit (a preview unless `--apply`), writes `shift-prep.json` listing every change, and leaves alone and reports what it does not handle yet: pointers into data or bss. The next no-change test is the same one for the *layout* mode, once it exists.
3. **Growth test:** insert code at the start of the main segment and rebuild. Check that it links, that the checksums are valid, and that a normalized comparison holds: every function, with its calls, data references and jump-table
   entries mapped through the old-to-new addresses, equals the original. A reference the build failed to relocate shows up as a mismatch.
4. **Execution test** where possible: run functions in a MIPS emulator (Unicorn) before and after the shift and compare results. Not available in this project's dependencies, so a test that needs it would skip without it.

## What exists now (0.11.3), and what it was verified against

`decomp shift-prep --layout` (after `--apply`) gives a tree the current `build.py` and marks `build.json` with `"layout": "shift"`. In that layout each segment follows the one before it, the code and data inside follow each other in their original order, the bss follows
the data, a raw segment after the code follows the code, and the segment-end symbols are computed by the linker. The build refuses, with the reasons, unless the audit says every reference is a symbol, and refuses games with a global pointer, symbols pinned inside the program, or C functions
that keep data of their own. After a link that differs from the original (a tree changed on purpose) it reports what moved and recomputes the header checksums: the family is found by reproducing the original's stored checksums, so a checksum is never written for a boot chip that was not verified
(only the 6102/7101 family, which the demo ROM is, is supported).

On the demo: an unchanged tree rebuilds the **identical** ROM in the shifting layout (also with a function written in C); growing the first function by 16 bytes grows the ROM by exactly 16, and an independent checker that reads the old ROM, the new ROM, the linker's symbol table and the assembly listing
accounts for **all 8,108 instructions** (the 96 functions and the start-up stub, which reads the linker's segment symbols and the address of `main`) (each call, jump and address load must hold where its symbol now is, and every other word must be unchanged) and for every data word after the code; the header checksums are valid. Growing by one instruction moves everything by exactly four bytes.

**Pointers into data and bss are not handled, and cannot be verified on the demo:** it has none (its only data word that looks like an address and points outside the program is a constant), so there is no real instance to rebuild and check, and code written without one would be unverified code. They need a real game.

**What the demo cannot tell you:** its functions are packed back to back, with no padding at all. The rule for padding (rebuilt as alignment where the original was aligned, otherwise as a count of bytes) is tested only on hand-computed cases and on the original-size rule, never on a game that has padding, and the C-function case is
tested for one function with no data of its own. **A tree changed on purpose cannot be compared with the original**, so the build can only say what moved, not that it is right: what stands between you and a silently wrong ROM is the refusal above, and the tests that an unchanged tree is identical.

## Out of scope for a first version (and the docs must say so)

Overlays and code loaded later, compressed segments, ROM-offset tables and DMA tables inside the game (code growing moves what they point at), code that builds addresses arithmetically, and boot chips other than 6102 until they are checked. Real
games (Super Mario 64, GoldenEye, Perfect Dark, the ones the README says are tested) have all of these; **a version that grows the main program's code in a demo-class ROM would be honest to ship, but must not be described as working on those games.**
