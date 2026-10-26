"""The N64 header checksum: checked against a real value (the demo ROM's own header), never assumed."""

from __future__ import annotations

import struct
from pathlib import Path

from decompnet.rom import n64crc

DEMO = (Path(__file__).resolve().parents[2] / "src" / "decompnet" / "app" / "static" / "demo" / "demo-quest-64.z64").read_bytes()


def test_the_algorithm_reproduces_the_checksums_stored_in_a_real_rom():
    assert n64crc.stored(DEMO) == (0x6C8D30EB, 0x81EE9BCF)  # what the demo's header says
    assert n64crc.crc(DEMO, n64crc.SEEDS["CIC-6102/7101 family"]) == (0x6C8D30EB, 0x81EE9BCF)  # what the algorithm computes: the same two numbers
    assert n64crc.identify(DEMO) == "CIC-6102/7101 family"


def test_a_rom_with_a_changed_byte_gets_the_checksums_recomputed_and_they_are_valid():
    changed = bytearray(DEMO)
    changed[0x2000] ^= 0xFF
    assert n64crc.identify(bytes(changed)) is None  # the stored checksums no longer match the content
    fixed, note = n64crc.fix(bytes(changed), DEMO)
    assert "recomputed" in note and n64crc.identify(fixed) == "CIC-6102/7101 family"
    assert fixed[:0x10] == DEMO[:0x10] and fixed[0x18:] == bytes(changed)[0x18:]  # only the eight checksum bytes were touched
    assert fixed != bytes(changed)


def test_a_rom_that_already_has_valid_checksums_is_left_exactly_as_it_is():
    fixed, _ = n64crc.fix(DEMO, DEMO)
    assert fixed == DEMO


def test_a_longer_rom_has_its_checksums_computed_over_the_same_first_megabyte():
    longer = DEMO + b"\0" * 16
    fixed, _ = n64crc.fix(longer, DEMO)
    assert fixed == longer  # growing the file after the first megabyte changes nothing the checksums cover


def test_nothing_is_written_when_the_original_is_not_a_kind_this_can_recompute():
    other = bytearray(DEMO)
    other[0x10:0x18] = struct.pack(">II", 0x12345678, 0x9ABCDEF0)  # checksums that no known seed reproduces
    rom = bytearray(DEMO)
    rom[0x2000] ^= 1
    fixed, note = n64crc.fix(bytes(rom), bytes(other))
    assert fixed == bytes(rom) and "not ones this tool can recompute" in note and "may refuse" in note


def test_short_or_empty_input_does_not_crash():
    assert n64crc.identify(b"") is None and n64crc.identify(b"\0" * 8) is None
    assert n64crc.fix(b"", b"")[0] == b""
