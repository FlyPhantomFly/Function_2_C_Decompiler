"""Matching integrity: the one thing this program must never get wrong is calling two different functions a match.

`scoring.diff` says a function matches when its score is 0, and everything downstream (credit, exports, the ROM) trusts
that. These tests pin the properties that make a 0 trustworthy:

- a score of 0 happens exactly when the two functions are the same: same code once relocation fields are masked, and the
  same relocations; never for anything less, never withheld from the real thing;
- the relocation masks are exact: they ignore the bits a linker will fill in and no others (17 table entries, every bit);
- the scores a near miss gets keep their documented order (a register swap is cheaper than a reorder, and so on);
- on real compiler output no change to any byte outside a relocation can survive.

One weakness is known and kept visible: `FunctionObj.fingerprint()` hashes the code and the relocation list as one
unframed stream, so a longer function can borrow a shorter one's fingerprint. It is a strict xfail here until fixed.
"""

from __future__ import annotations

import math
import random
import shutil
import subprocess
import tomllib
from pathlib import Path

import capstone
import pytest

from decompnet import scoring
from decompnet.elfobj import _MASKS, FunctionObj, Reloc, extract_function, list_functions

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "projects" / "demo"


def x86(hex_bytes: str, relocs=()) -> FunctionObj:
    return FunctionObj("f", "x86_64", False, bytes.fromhex(hex_bytes.replace(" ", "")), list(relocs))


def mips(*words: int, relocs=()) -> FunctionObj:
    return FunctionObj("f", "mips", True, b"".join(w.to_bytes(4, "big") for w in words), list(relocs))


def same_function(a: FunctionObj, b: FunctionObj) -> bool:
    """The definition of 'the same function', spelled out without the hash: equal masked code, equal relocations."""
    return a.normalized() == b.normalized() and sorted(r.key() for r in a.relocs) == sorted(r.key() for r in b.relocs)


# ---- the scores of near misses ------------------------------------------------------------------------------------

BASE = "89 d8  83 c0 01  c3"  # mov eax, ebx ; add eax, 1 ; ret


def test_the_penalties_keep_their_order():
    p = scoring
    assert p.PENALTY_STACKDIFF < p.PENALTY_REGALLOC < p.PENALTY_OPERAND < p.PENALTY_REORDER < p.PENALTY_INSERTION
    assert p.PENALTY_REORDER < p.PENALTY_DELETION


@pytest.mark.parametrize("name, target, candidate, penalty, marker", [
    ("a register swap", BASE, "89 d9  83 c0 01  c3", scoring.PENALTY_REGALLOC, "r"),
    ("a different constant", BASE, "89 d8  83 c0 02  c3", scoring.PENALTY_OPERAND, "i"),
    ("a stack offset", "8b 45 fc  c3", "8b 45 f8  c3", scoring.PENALTY_STACKDIFF, "s"),
    ("a missing instruction", BASE, "89 d8  c3", scoring.PENALTY_DELETION, "<"),
    ("an extra instruction", "89 d8  c3", BASE, scoring.PENALTY_INSERTION, ">"),
    ("one instruction moved", "83 c0 01  83 e9 01  c3", "83 e9 01  83 c0 01  c3", scoring.PENALTY_REORDER, "o"),
])
def test_each_kind_of_near_miss_costs_exactly_its_penalty(name, target, candidate, penalty, marker):
    d = scoring.diff(x86(target), x86(candidate))
    assert d.score == penalty, name
    assert not d.bytes_match and d.percent < 100
    assert marker in {m for m, *_ in d.rows}


def test_a_register_swap_is_cheaper_than_a_reorder_which_is_cheaper_than_a_real_insertion():
    swap = scoring.diff(x86(BASE), x86("89 d9  83 c0 01  c3")).score
    reorder = scoring.diff(x86("83 c0 01  83 e9 01  c3"), x86("83 e9 01  83 c0 01  c3")).score
    insertion = scoring.diff(x86("89 d8  c3"), x86(BASE)).score
    assert 0 < swap < reorder < insertion


def test_identical_functions_score_zero_and_read_one_hundred_percent():
    d = scoring.diff(x86(BASE), x86(BASE))
    assert (d.score, d.bytes_match, d.percent) == (0, True, 100.0)
    assert {m for m, *_ in d.rows} == {" "}


def test_the_same_instruction_text_in_a_different_encoding_is_not_a_match():
    """`mov eax, ebx` can be 89 d8 or 8b c3. Same words on screen, different bytes: it must score 1, never 0."""
    d = scoring.diff(x86("89 d8 c3"), x86("8b c3 c3"))
    assert d.score == 1 and not d.bytes_match


# ---- a score of 0 means the same function, and only that ----------------------------------------------------------


def _random_function(rng: random.Random) -> FunctionObj:
    code = bytes(rng.randrange(256) for _ in range(rng.randrange(4, 40)))
    relocs = [Reloc(rng.randrange(0, max(1, len(code) - 3)), rng.choice((2, 4)), rng.choice("ab"), rng.choice((0, 4)))
              for _ in range(rng.randrange(0, 3))]
    return FunctionObj("f", "x86_64", False, code, relocs)


def _mutate(rng: random.Random, f: FunctionObj) -> FunctionObj:
    code, relocs = bytearray(f.code), list(f.relocs)
    kind = rng.randrange(8)
    if kind == 1:
        code[rng.randrange(len(code))] ^= 1 << rng.randrange(8)
    elif kind == 2 and len(code) > 1:
        i, j = rng.sample(range(len(code)), 2)
        code[i], code[j] = code[j], code[i]
    elif kind == 3 and len(code) > 4:
        del code[-rng.randrange(1, 4):]
    elif kind == 4:
        code += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 4)))
    elif kind == 5 and relocs:
        r = relocs[rng.randrange(len(relocs))]
        relocs[relocs.index(r)] = Reloc(r.offset, r.type, r.symbol + "x", r.addend)
    elif kind == 6 and relocs:
        relocs.pop(rng.randrange(len(relocs)))
    elif kind == 7:
        relocs.append(Reloc(rng.randrange(0, max(1, len(code) - 3)), 2, "c", 0))
    return FunctionObj(f.name, f.arch, f.big_endian, bytes(code), relocs)


def test_a_score_of_zero_happens_exactly_when_the_functions_are_the_same():
    rng = random.Random(0xDEC0)
    zero = nonzero = crashed = 0
    for _ in range(600):
        a = _random_function(rng)
        b = _mutate(rng, a)
        try:
            d = scoring.diff(a, b)
        except capstone.CsError:  # a relocation inside undecodable bytes: its own known bug, pinned by the xfail below
            crashed += 1
            continue
        want = same_function(a, b)
        assert (d.score == 0) == want and d.bytes_match == want, (a, b)
        zero += want
        nonzero += not want
    assert zero > 50 and nonzero > 250  # the sweep really exercised both outcomes
    assert crashed < 120


# ---- relocations: normalization ignores exactly what a linker fills in ------------------------------------------


@pytest.mark.parametrize("arch, rtype", sorted(_MASKS))
def test_every_relocation_mask_clears_its_field_bits_and_no_others(arch, rtype):
    delta, length, mask = _MASKS[(arch, rtype)]
    big = arch in ("mips", "ppc")
    base = FunctionObj("f", arch, big, b"\xa5" * 16, [Reloc(0, rtype, "sym", 0)])
    for bit in range(16 * 8):
        byte = bit // 8
        flipped = bytearray(base.code)
        flipped[byte] ^= 1 << (bit % 8)
        other = FunctionObj("f", arch, big, bytes(flipped), [Reloc(0, rtype, "sym", 0)])
        in_field = delta <= byte < delta + length
        if in_field:
            place = (delta + length - 1 - byte) * 8 + bit % 8 if big else (byte - delta) * 8 + bit % 8
            ignored = bool((mask >> place) & 1)
        else:
            ignored = False
        assert (base.fingerprint() == other.fingerprint()) == ignored, (arch, rtype, "bit", bit)


@pytest.mark.parametrize("arch, rtype", [("x86_64", 2), ("x86_64", 4), ("mips", 3), ("ppc", 1), ("arm", 3)])
def test_a_relocation_type_with_no_table_entry_masks_exactly_four_bytes(arch, rtype):
    assert (arch, rtype) not in _MASKS
    big = arch in ("mips", "ppc")
    base = FunctionObj("f", arch, big, b"\xa5" * 12, [Reloc(2, rtype, "sym", 0)])
    for byte in range(12):
        flipped = bytearray(base.code)
        flipped[byte] ^= 0x01
        other = FunctionObj("f", arch, big, bytes(flipped), [Reloc(2, rtype, "sym", 0)])
        assert (base.fingerprint() == other.fingerprint()) == (2 <= byte < 6), byte


LUI = 0x3C041234  # lui $a0, 0x1234
ADDIU = 0x24845678  # addiu $a0, $a0, 0x5678
JR = 0x03E00008
NOP = 0


def _hi_lo(symbol="foo", hi_type=5, hi_addend=0, lo_off=4, lo_addend=0, lo=True, extra=()):
    relocs = [Reloc(0, hi_type, symbol, hi_addend)] + ([Reloc(lo_off, 6, "foo", lo_addend)] if lo else []) + list(extra)
    return relocs


def test_what_a_linker_fills_in_is_ignored_on_real_mips_relocations():
    target = mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo())
    unlinked = mips(0x3C040000, 0x24840000, JR, NOP, relocs=_hi_lo())  # immediates still zero: the object file's form
    d = scoring.diff(target, unlinked)
    assert d.score == 0 and d.bytes_match


@pytest.mark.parametrize("what, candidate", [
    ("a different symbol", mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo(symbol="bar"))),
    ("a different relocation type on the same bits", mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo(hi_type=6))),
    ("a different addend", mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo(hi_addend=4))),
    ("a relocation moved to another instruction", mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo(lo_off=8))),
    ("a relocation missing", mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo(lo=False))),
    ("an extra relocation", mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo(extra=[Reloc(8, 4, "baz", 0)]))),
    ("the register field next to the masked immediate", mips(0x3C051234, ADDIU, JR, NOP, relocs=_hi_lo())),
    ("the opcode next to the masked immediate", mips(0x34041234, ADDIU, JR, NOP, relocs=_hi_lo())),
])
def test_a_relocation_can_never_be_traded_for_a_different_one_or_hide_a_neighbouring_bit(what, candidate):
    target = mips(LUI, ADDIU, JR, NOP, relocs=_hi_lo())
    d = scoring.diff(target, candidate)
    assert target.fingerprint() != candidate.fingerprint(), what
    assert d.score > 0 and not d.bytes_match, what


def test_the_bits_beside_a_call_target_are_still_compared():
    """jal and j differ only in an opcode bit next to the 26-bit target the relocation covers."""
    jal = mips(0x0C000000, NOP, relocs=[Reloc(0, 4, "func", 0)])
    j = mips(0x08000000, NOP, relocs=[Reloc(0, 4, "func", 0)])
    assert scoring.diff(jal, mips(0x0C123456, NOP, relocs=[Reloc(0, 4, "func", 0)])).score == 0  # the target bits: masked
    assert scoring.diff(jal, j).score > 0


def test_a_ppc_call_and_a_plain_branch_are_not_the_same_function():
    """bl and b differ in the low LK bit, which R_PPC_REL24's mask deliberately leaves alone."""
    bl = FunctionObj("f", "ppc", True, (0x48000001).to_bytes(4, "big"), [Reloc(0, 10, "func", 0)])
    b = FunctionObj("f", "ppc", True, (0x48000000).to_bytes(4, "big"), [Reloc(0, 10, "func", 0)])
    assert scoring.diff(bl, b).score > 0


# ---- percentages never claim more than is true -----------------------------------------------------------------


def test_a_percentage_reads_100_only_for_a_real_match():
    assert scoring.percent_text(100.0) == "100%" and scoring.percent_text(250.0) == "100%"
    for p in (99.99, 99.95, 99.9999999, math.nextafter(100.0, 0.0), 99.0):
        assert scoring.percent_text(p) != "100%" and scoring.percent_text(p) != "100.0%", p
    assert scoring.percent_text(None) == "?" and scoring.percent_text(-3.0) == "0.0%"


def test_the_percentage_of_a_near_miss_is_between_zero_and_one_hundred():
    for target, candidate in [(BASE, "89 d9 83 c0 01 c3"), (BASE, "c3"), ("c3", BASE), (BASE, "90 90 90 90 90 90 90 90")]:
        d = scoring.diff(x86(target), x86(candidate))
        assert 0.0 <= d.percent < 100.0 and scoring.percent_text(d.percent) != "100%"


# ---- real compiler output ---------------------------------------------------------------------------------------

needs_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="needs gcc to build the demo project's objects")


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    """The demo project's 13 real functions compiled at -O2 (twice) and at -O0."""
    cfg = tomllib.loads((DEMO / "project.toml").read_text(encoding="utf-8"))
    work = tmp_path_factory.mktemp("corpus") / "demo"
    shutil.copytree(DEMO, work, ignore=shutil.ignore_patterns("target"))
    (work / "target").mkdir()
    built = {}
    for label, swap in (("O2", None), ("O2 again", None), ("O0", ("-O2", "-O0"))):
        cmd = [a.replace(*swap) if swap else a for a in cfg["target"]["build"]]
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)
        built[label] = (work / "target" / "game.o").read_bytes()
    return built


def _covered(f: FunctionObj) -> set[int]:
    out: set[int] = set()
    for r in f.relocs:
        delta, length, _ = _MASKS.get((f.arch, r.type), (0, 4, 0))
        out |= set(range(r.offset + delta, r.offset + delta + length))
    return out


@needs_gcc
def test_compiling_the_same_source_twice_gives_functions_that_match_each_other(corpus):
    names = list_functions(corpus["O2"])
    assert len(names) >= 10
    for name in names:
        a, b = extract_function(corpus["O2"], name), extract_function(corpus["O2 again"], name)
        d = scoring.diff(a, b)
        assert d.score == 0 and d.bytes_match and a.fingerprint() == b.fingerprint(), name


@needs_gcc
def test_no_byte_of_a_real_function_can_change_without_losing_the_match(corpus):
    flips = 0
    for name in list_functions(corpus["O2"]):
        f = extract_function(corpus["O2"], name)
        skip = _covered(f)
        for i in range(len(f.code)):
            if i in skip:
                continue
            for bit in (0, 7):
                code = bytearray(f.code)
                code[i] ^= 1 << bit
                d = scoring.diff(f, FunctionObj(f.name, f.arch, f.big_endian, bytes(code), f.relocs))
                assert d.score > 0 and not d.bytes_match, (name, i, bit)
                flips += 1
    assert flips > 800


@needs_gcc
def test_the_bytes_a_relocation_will_fill_in_can_change_on_real_functions_and_still_match(corpus):
    changed = 0
    for name in list_functions(corpus["O2"]):
        f = extract_function(corpus["O2"], name)
        for i in sorted(_covered(f)):
            if i < len(f.code):
                code = bytearray(f.code)
                code[i] ^= 0xFF
                d = scoring.diff(f, FunctionObj(f.name, f.arch, f.big_endian, bytes(code), f.relocs))
                assert d.score == 0 and d.bytes_match, (name, i)
                changed += 1
    assert changed > 20


@needs_gcc
def test_the_same_function_at_a_different_optimization_level_never_matches(corpus):
    for name in list_functions(corpus["O2"]):
        d = scoring.diff(extract_function(corpus["O2"], name), extract_function(corpus["O0"], name))
        assert d.score > 0 and not d.bytes_match, name


# ---- the known weakness -----------------------------------------------------------------------------------------


def _forged_longer_function() -> tuple[FunctionObj, FunctionObj]:
    """A target with one relocation, and a longer function with none whose bytes are the target's masked code followed by
    the text of that relocation's key. fingerprint() feeds both into the hash with nothing between them."""
    reloc = Reloc(offset=2, type=2, symbol="foo", addend=0)
    target = FunctionObj("t", "x86_64", False, b"\x90" * 8, [reloc])
    forged = FunctionObj("f", "x86_64", False, target.normalized() + repr(reloc.key()).encode(), [])
    return target, forged


def test_known_limitation_the_fingerprint_alone_cannot_tell_these_two_functions_apart():
    """Documents what remains of the weakness, so nobody decides a match by fingerprint equality alone: use
    FunctionObj.same_as when both functions are at hand, and the stored size too in hash-only projects. If this ever
    fails because the fingerprint was reframed (a stored-data migration), delete it in that change."""
    target, forged = _forged_longer_function()
    assert len(forged.code) > len(target.code) and not forged.relocs and target.relocs
    assert target.fingerprint() == forged.fingerprint()


def test_diff_does_not_call_a_longer_function_a_match_for_a_shorter_one():
    target, forged = _forged_longer_function()
    d = scoring.diff(target, forged)
    assert d.score > 0 and not d.bytes_match


# ---- a function that cannot be scored at all -------------------------------------------------------------------


@pytest.mark.xfail(strict=True, raises=capstone.CsError,
                   reason="x86 only: a relocation inside bytes capstone cannot decode raises instead of scoring (fixed in a later version)")
def test_a_relocation_inside_undecodable_bytes_is_scored_not_a_crash():
    """`86 0d` is a truncated instruction, so capstone's SKIPDATA mode yields `.byte` pseudo-instructions; _symbolize then
    reads `ins.disp_size`, which capstone refuses for them. Fails closed (no false match), but the function can never be
    scored, not even against itself. Data in code with relocations (jump tables in .text) would do the same."""
    f = FunctionObj("f", "x86_64", False, bytes.fromhex("860d"), [Reloc(1, 2, "a", 0)])
    d = scoring.diff(f, f)
    assert d.score == 0 and d.bytes_match


@pytest.mark.parametrize("arch, big, code, rtype", [("mips", True, "ffffffff", 5), ("ppc", True, "ffffffff", 10),
                                                    ("arm", False, "ffffffff", 28), ("thumb", False, "ffffffff", 2)])
def test_the_other_architectures_score_a_relocation_inside_undecodable_bytes(arch, big, code, rtype):
    f = FunctionObj("f", arch, big, bytes.fromhex(code), [Reloc(0, rtype, "a", 0)])
    assert scoring.diff(f, f).score == 0
