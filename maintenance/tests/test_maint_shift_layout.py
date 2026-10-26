"""The shifting layout: code can grow, and the references to everything that moved are rebuilt to point at where it went.

Two kinds of test. A tree nobody changed must rebuild the identical ROM in the shifting layout (the proof that the layout itself changes nothing). And a tree whose code was made bigger must build, with
every word that changed explained by an independent checker as the relocation of a named symbol: it reads the original ROM, the new ROM, the linker's own symbol table and the assembly listing, and
accepts nothing it cannot account for. The checker is itself tested by breaking a ROM, since one that cannot fail proves nothing.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from shift_fixture import tree as synthetic_tree

from decompnet.app import cli
from decompnet.rom import n64crc, shiftaudit, shiftprep

ROOT = Path(__file__).resolve().parents[2]


def _problem() -> str:
    sys.path.insert(0, str(ROOT / "maintenance" / "tools"))
    import eval_agent

    return eval_agent.problem()


needs_demo = pytest.mark.skipif(bool(_problem()), reason=_problem() or "")
GROW = "asm/nonmatchings/main/func_80000460.s"


@pytest.fixture
def demo(tmp_path):
    from decompnet.app.engine import RomNetwork

    home = tmp_path / "home"
    (home / ".decomp").mkdir(parents=True)
    net = RomNetwork(home / ".decomp" / "decomp.db", home)
    slug = net.import_rom((ROOT / "src" / "decompnet" / "app" / "static" / "demo" / "demo-quest-64.z64").read_bytes(), confirmed=True, name="demo-quest-64.z64", log=lambda *_: None)
    net.export_rom(slug, log=lambda *_: None)
    return home / slug / "source"


def run_build(root: Path) -> tuple[int, str]:
    done = subprocess.run([sys.executable, "build.py"], cwd=root, capture_output=True, text=True, timeout=600)
    return done.returncode, (done.stdout + done.stderr).strip()


def shifted(root: Path) -> Path:
    shiftprep.prepare(root, apply=True)
    shiftprep.enable_layout(root)
    return root


# ---- the independent checker -------------------------------------------------------------------------------------------------------------------------------

INSN = re.compile(r"^\s*/\*\s*([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s*\*/\s+(\S+)\s*(.*?)\s*$")
HILO = re.compile(r"%(hi|lo)\(\s*([\w.]+)\s*(?:\+\s*(0x[0-9A-Fa-f]+|\d+))?\s*\)")


def elf_symbols(path: Path) -> dict[str, int]:
    from elftools.elf.elffile import ELFFile

    with open(path, "rb") as f:
        return {s.name: s["st_value"] for s in ELFFile(f).get_section_by_name(".symtab").iter_symbols() if s.name}


def check_moved_rom(root: Path, old: bytes, new: bytes) -> list[str]:
    """Every word of every function and of the data, old against new. Equal is fine; different must be exactly the relocation of a named symbol. Returns what it could not explain."""
    build = json.loads((root / "build.json").read_text(encoding="utf-8"))
    syms = elf_symbols(root / "build" / "game.elf")
    problems: list[str] = []
    seen = 0  # a checker that looks at nothing reports nothing: count what it looked at, and fail if that is not everything
    word = lambda rom, at: int.from_bytes(rom[at:at + 4], "big")  # noqa: E731
    for fn in build["functions"]:
        delta = syms[fn["name"]] - fn["vram"]
        for line in (root / fn["asm"]).read_text(encoding="utf-8").splitlines():
            m = INSN.match(line)
            if not m:
                continue
            rom, vram, w, mnem, ops = int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16), m.group(4), m.group(5)
            seen += 1
            if word(old, rom) != w:
                problems.append(f"{fn['name']} {vram:#x}: the listing does not match the original ROM")
                continue
            got = word(new, rom + delta)
            # a reference must hold where its symbol is NOW, which is not the same as "the word did not change": a call left at its old value is the very bug this must catch
            if mnem in ("jal", "j") and re.fullmatch(r"\.L[0-9A-Fa-f]{8}|[A-Za-z_]\w*", ops):
                target = int(ops[2:], 16) + delta if ops.startswith(".L") else syms.get(ops)
                want = None if target is None else (w & 0xFC000000) | ((target >> 2) & 0x3FFFFFF)
            elif (h := HILO.search(ops)) and h.group(2) in syms:
                addr = syms[h.group(2)] + (int(h.group(3), 0) if h.group(3) else 0)
                want = (w & 0xFFFF0000) | (((addr + 0x8000) >> 16) & 0xFFFF if h.group(1) == "hi" else addr & 0xFFFF)
            else:
                want = w  # not a reference: it must be exactly what it was
            if want != got:
                problems.append(f"{fn['name']} {vram:#x} {mnem} {ops}: {w:#010x} became {got:#010x}, expected {'(no explanation)' if want is None else f'{want:#010x}'}")
    for path in sorted((root / "asm" / "data").glob("**/*.s")):
        if "bss" in path.name:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        first = next(((n, m) for n, line in enumerate(lines) for m in [re.match(r"\s*dlabel\s+(\S+)", line)] if m), None)
        if not first:
            continue
        v0 = int(re.search(r"/\*\s*[0-9A-Fa-f]+\s+([0-9A-Fa-f]{8})", lines[first[0] + 1]).group(1), 16)
        delta = syms[first[1].group(1)] - v0
        for line in lines:
            m = re.match(r"\s*/\*\s*([0-9A-Fa-f]+)\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s*\*/\s*\.word\s+(\S+)\s*$", line)
            if not m:
                continue
            rom, w, operand = int(m.group(1), 16), int(m.group(3), 16), m.group(4)
            got = word(new, rom + delta)
            want = syms.get(operand) if re.fullmatch(r"[A-Za-z_]\w*", operand) else w
            if want is None or got != want:
                problems.append(f"{path.name} {rom:#x} .word {operand}: {w:#010x} became {got:#010x}, expected {'?' if want is None else f'{want:#010x}'}")
    covered = sum(1 for fn in build["functions"] for line in (root / fn["asm"]).read_text(encoding="utf-8").splitlines() if INSN.match(line))
    if seen == 0 or seen != covered:
        problems.append(f"the checker looked at {seen} instructions of {covered}")
    grown = len(new) - len(old)
    if new[0x18:0x1000] != old[0x18:0x1000] or new[:0x10] != old[:0x10]:
        problems.append("the header or boot code changed")
    last = max(s["start"] for s in build["segments"])
    if new[last + grown:] != old[last:]:
        problems.append("the raw segment after the code is not the same bytes, moved")
    return problems


# ---- turning it on ---------------------------------------------------------------------------------------------------------------------------------------


def test_the_layout_is_refused_while_references_are_still_numbers_and_says_what_to_do(tmp_path):
    with pytest.raises(shiftaudit.AuditError, match="not ready.*shift-prep --apply"):
        shiftprep.enable_layout(synthetic_tree(tmp_path))


def test_the_command_switches_the_layout_keeps_the_old_build_and_is_safe_to_repeat(tmp_path, capsys):
    clean = "glabel func_80000460\n    /* 1060 80000460 3C048000 */  lui        $a0, %hi(D_800082B0)\n    /* 1064 80000464 03E00008 */  jr         $ra\n"
    root = synthetic_tree(tmp_path, {"func_80000460": (0x80000460, clean)}, data="dlabel D_800082B0\n    /* 8EB0 800082B0 80000460 */ .word func_80000460\n")
    (root / "build.py").write_text("# the old build\n", encoding="utf-8")
    assert cli.main(["shift-prep", str(root), "--layout"]) == 0
    assert "now a shifting one (build.py, build.json)" in capsys.readouterr().out
    assert json.loads((root / "build.json").read_text())["layout"] == "shift"
    assert (root / "build.py.before-shift").read_text() == "# the old build\n" and "shift_linker_script" in (root / "build.py").read_text()
    assert shiftprep.enable_layout(root)["changed"] == []  # a second time: nothing to change, and the first backup is not overwritten
    assert (root / "build.py.before-shift").read_text() == "# the old build\n"


# ---- the real demo -----------------------------------------------------------------------------------------------------------------------------------------


@needs_demo
def test_a_tree_nobody_changed_rebuilds_the_identical_rom_in_the_shifting_layout(demo):
    """The proof that the layout itself changes nothing: pinned and shifting builds of the same tree are the same bytes."""
    assert run_build(demo)[1].startswith("identical: ")
    shifted(demo)
    code, line = run_build(demo)
    assert code == 0 and line.startswith("identical: "), line
    script = (demo / "build" / "game.ld").read_text(encoding="utf-8")
    assert "SHIFTING layout" in script and "LOADADDR(" in script
    assert not re.search(r"^\s+\. = 0x[0-9A-F]+; (?!\S+\.bss\.o\(\.bss)", script, re.M)  # no code or data is pinned to an offset any more (only the bss keeps its own internal offsets)


@needs_demo
def test_growing_a_function_moves_everything_after_it_and_every_reference_follows(demo):
    old = (demo / "baserom.z64").read_bytes()
    shifted(demo)
    path = demo / GROW
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + "    nop\n" * 4, encoding="utf-8")  # 16 more bytes in the first function
    code, line = run_build(demo)
    assert code == 0 and line.startswith("rebuilt with a shifting layout") and f"{len(old) + 16} bytes against the original's {len(old)}" in line and "checksums recomputed" in line, line
    new = (demo / "build" / "game.z64").read_bytes()
    assert len(new) == len(old) + 16 and n64crc.identify(new) == "CIC-6102/7101 family"  # the file grew by exactly what was added, and a console would accept its header
    assert check_moved_rom(demo, old, new) == []  # all 96 functions, every call, jump, address load and table entry, and the data after the code
    syms = elf_symbols(demo / "build" / "game.elf")
    assert syms["func_80000460"] == 0x80000460 and syms["main_VRAM_END"] > 0 and syms["main_ROM_END"] == 0xB5A0 + 16


@needs_demo
def test_growing_by_one_instruction_on_the_packed_demo_moves_everything_by_exactly_those_four_bytes(demo):
    """The demo's functions are packed back to back (the generated script needs no padding statement at all, and only 31 of its 96 functions start on a 16-byte boundary, by coincidence), so there is
    no padding to absorb a change: everything after moves by exactly the bytes added, and every reference follows."""
    old = (demo / "baserom.z64").read_bytes()
    shifted(demo)
    path = demo / GROW
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n    nop\n", encoding="utf-8")
    assert run_build(demo)[0] == 0
    new = (demo / "build" / "game.z64").read_bytes()
    script = (demo / "build" / "game.ld").read_text(encoding="utf-8")
    assert "ALIGN(" not in script.replace("SUBALIGN(", "") and not re.search(r"^\s+\. = \. \+", script, re.M)  # no padding to preserve: the policy below is tested on its own
    assert len(new) == len(old) + 4 and check_moved_rom(demo, old, new) == [] and n64crc.identify(new) == "CIC-6102/7101 family"


def load_template(tmp_path: Path):
    """The generator code that ends up in every exported build.py, imported from a copy with an empty build.json, so that its helpers can be tested on their own."""
    import importlib.util
    import shutil

    d = tmp_path / "template"
    d.mkdir()
    shutil.copyfile(ROOT / "src" / "decompnet" / "rom" / "export_build.py", d / "build.py")
    (d / "build.json").write_text("{}", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("template_build", d / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_function_keeps_the_size_it_had_in_the_original_even_after_it_has_grown(tmp_path):
    """In a shifting layout the padding after a function is measured from where the function ENDED in the original, not from what it has become, or a function that grew would swallow the gap after it.
    The demo has no gaps, so this is tested on the generator's own function: the size comes from the original listing, and lines added since do not count."""
    module = load_template(tmp_path)
    module.LAYOUT = "shift"
    module.ROOT = tmp_path
    (tmp_path / "f.s").write_text("glabel f\n    /* 1060 80000460 27BDFFE8 */  addiu $sp, $sp, -0x18\n    /* 1064 80000464 03E00008 */  jr $ra\n    /* 1068 80000468 00000000 */  nop\n    nop\n    nop\n    nop\n", encoding="utf-8")
    assert module._fn_size({"asm": "f.s", "vram": 0x80000460, "name": "f"}, {}) == 0xC  # three listed instructions; the three added nops are not part of what it was


@pytest.mark.parametrize("cursor, v, kind, amount", [
    (0x80000018, 0x80000020, "ALIGN", 16),  # 8 zero bytes up to a 16-byte boundary: it was alignment
    (0x80000014, 0x80000018, "ALIGN", 8),  # 4 bytes up to an 8-byte boundary
    (0x80000010, 0x80000014, "bytes", 4),  # 4 bytes that end on no boundary above 4: a fixed gap
    (0x80000008, 0x80000030, "bytes", 0x28),  # a gap of 40 is more than any alignment explains
    (0x80000018, 0x80000028, "bytes", 0x10),  # 16 bytes up to an 8-byte boundary: more than 8-byte alignment explains
])
def test_zero_padding_between_items_is_rebuilt_as_alignment_where_it_was_alignment_and_as_a_count_where_it_was_not(tmp_path, cursor, v, kind, amount):
    line = load_template(tmp_path)._pad(cursor, v)
    if kind == "ALIGN":
        assert line.strip() == f". = ALIGN({amount});"
        assert -(-cursor // amount) * amount == v  # and it reproduces the original gap exactly
        assert -(-(cursor + 4) // amount) * amount % amount == 0  # after the item before it grows by 4, the next one still starts on the boundary
    else:
        assert line.strip() == f". = . + 0x{amount:X};" and cursor + amount == v


@needs_demo
def test_a_function_written_in_c_is_built_the_same_way_in_the_shifting_layout(demo):
    """C objects are trimmed and placed like the rest: matching one in C and rebuilding in the shifting layout must still give the identical ROM."""
    sys.path.insert(0, str(ROOT / "maintenance" / "tools"))
    import eval_agent

    shifted(demo)
    src = demo / "src" / "main"
    src.mkdir(parents=True, exist_ok=True)
    (src / "func_800007F4.c").write_text('#include "common.h"\n' + eval_agent.ABS + "\n", encoding="utf-8")
    done = subprocess.run([sys.executable, "build.py", "check", "func_800007F4"], cwd=demo, capture_output=True, text=True, timeout=600)
    assert done.returncode == 0 and "identical to the original" in done.stdout, done.stdout + done.stderr
    code, line = run_build(demo)
    assert code == 0 and line.startswith("identical: ") and "(1 of 96 functions in C)" in line, line


@needs_demo
def test_the_checker_is_not_a_rubber_stamp_it_fails_on_a_rom_with_one_reference_left_behind(demo):
    old = (demo / "baserom.z64").read_bytes()
    shifted(demo)
    path = demo / GROW
    path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + "    nop\n" * 4, encoding="utf-8")
    assert run_build(demo)[0] == 0
    new = bytearray((demo / "build" / "game.z64").read_bytes())
    assert check_moved_rom(demo, old, bytes(new)) == []
    at = next(i for i in range(0x1060 + 16, 0x8000, 4) if (new[i] >> 2) == 3)  # a jal after the grown function: it was relocated by +16 bytes (+4 words)
    new[at:at + 4] = (int.from_bytes(new[at:at + 4], "big") - 4).to_bytes(4, "big")  # put it back to its OLD value: a call nobody relocated
    assert any("jal" in p for p in check_moved_rom(demo, old, bytes(new)))
    left = bytearray((demo / "build" / "game.z64").read_bytes())
    left[at:at + 4] = (int.from_bytes(left[at:at + 4], "big") - 1).to_bytes(4, "big")  # and one that aims a word early
    assert any("jal" in p for p in check_moved_rom(demo, old, bytes(left)))
    new2 = bytearray((demo / "build" / "game.z64").read_bytes())
    where = syms_value(demo, "jtgt_80000958")
    table = next(i for i in range(0x8000, len(new2) - 4, 4) if int.from_bytes(new2[i:i + 4], "big") == where)  # the jump-table entry that holds that label's address
    new2[table:table + 4] = (0x80000958).to_bytes(4, "big")  # now holding the OLD address
    assert any(".word jtgt_80000958" in p for p in check_moved_rom(demo, old, bytes(new2)))


def syms_value(root: Path, name: str) -> int:
    return elf_symbols(root / "build" / "game.elf")[name]


@needs_demo
def test_the_shifting_build_refuses_to_run_over_references_that_are_still_numbers(demo):
    shifted(demo)
    data = demo / "asm/data/8EB0.data.s"
    data.write_text(data.read_text(encoding="utf-8").rstrip("\n") + "\n    /* 9999 80009999 80000960 */ .word 0x80000960\n", encoding="utf-8")  # someone adds a raw address
    code, out = run_build(demo)
    assert code == 1 and "cannot be built with a shifting layout" in out and "absolute addresses" in out and "shift-prep" in out


@needs_demo
def test_the_shifting_build_refuses_a_game_with_a_global_pointer(demo):
    shifted(demo)
    build = json.loads((demo / "build.json").read_text())
    build["gp"] = 0x80008000
    (demo / "build.json").write_text(json.dumps(build))
    code, out = run_build(demo)
    assert code == 1 and "global pointer" in out
