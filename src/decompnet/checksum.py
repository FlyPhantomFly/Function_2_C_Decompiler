"""SHA-256 sidecar files, in the format `sha256sum --check` reads: `<64 hex digits>  <file name>` in `<file>.sha256`.

A checksum beside a backup says whether the file is still the file that was written: a damaged or truncated copy, a bad disk, a sync that stopped halfway.
It does not say who wrote it (whoever can change the file can change its sidecar too). It lives in its own module so that `store.py` (which keeps a copy before it migrates
a database) and the backup code can both use it without importing each other.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def sidecar(path: Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".sha256")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path: Path) -> str:
    """Write `<path>.sha256` for the file as it is now, and return the digest."""
    digest = sha256_file(path)
    sidecar(path).write_text(f"{digest}  {Path(path).name}\n", encoding="utf-8")
    return digest


def check(path: Path) -> bool | None:
    """True if the file matches its sidecar, False if it does not (or the sidecar is not a checksum), None if there is no sidecar to check against."""
    side = sidecar(path)
    if not side.exists():
        return None
    found = _LINE.match(side.read_text(encoding="utf-8", errors="replace").strip())
    return bool(found) and found.group(1) == sha256_file(path)
