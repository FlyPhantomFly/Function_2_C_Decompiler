"""The N64 header checksums (CRC1 and CRC2, bytes 0x10 to 0x17 of a big-endian ROM), for a ROM whose code has moved or grown.

The boot code checks them on a real console, and some emulators and flash carts do too, so any change to the first megabyte after the boot code leaves a ROM that may be refused until they are recomputed.
Only the boot-chip family whose seed is checked against a real ROM here (the CIC-6102 and 7101 family, which most games use) is supported. The family is never assumed: it is found by recomputing the
checksums of the ORIGINAL ROM with each known seed and keeping the one that reproduces the checksums stored in it. If none does (another boot chip, or an original whose checksums were not valid), nothing is
recomputed and the caller is told, so a wrong checksum is never written.
"""

from __future__ import annotations

import struct

START, LENGTH = 0x1000, 0x100000
SEEDS = {"CIC-6102/7101 family": 0xF8CA4DDC}
MASK = 0xFFFFFFFF


def crc(rom: bytes, seed: int) -> tuple[int, int]:
    t1 = t2 = t3 = t4 = t5 = t6 = seed
    data = bytes(rom[START:START + LENGTH]).ljust(LENGTH, b"\0")
    for (d,) in struct.iter_unpack(">I", data):
        if ((t6 + d) & MASK) < t6:
            t4 = (t4 + 1) & MASK
        t6 = (t6 + d) & MASK
        t3 ^= d
        shift = d & 0x1F
        r = ((d << shift) | (d >> (32 - shift))) & MASK if shift else d
        t5 = (t5 + r) & MASK
        t2 = t2 ^ r if t2 > d else t2 ^ t6 ^ d
        t1 = (t1 + (t5 ^ d)) & MASK
    return t6 ^ t4 ^ t3, t5 ^ t2 ^ t1


def stored(rom: bytes) -> tuple[int, int]:
    return struct.unpack(">II", rom[0x10:0x18])


def identify(rom: bytes) -> str | None:
    """The boot-chip family whose seed reproduces the checksums stored in this ROM, or None."""
    if len(rom) < 0x18:
        return None
    return next((name for name, seed in SEEDS.items() if crc(rom, seed) == stored(rom)), None)


def fix(rom: bytes, original: bytes) -> tuple[bytes, str]:
    """`rom` with its header checksums recomputed the way `original` has them. Returns the ROM and a sentence about what was done."""
    family = identify(original)
    if family is None:
        return rom, ("the original's header checksums are not ones this tool can recompute (another boot chip, or they were not valid), so they were left as built: "
                     "a real console may refuse the ROM")
    c1, c2 = crc(rom, SEEDS[family])
    fixed = bytearray(rom)
    fixed[0x10:0x18] = struct.pack(">II", c1, c2)
    return bytes(fixed), f"header checksums recomputed ({family})"
