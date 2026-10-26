#!/usr/bin/env python3
"""Check the pinned compiler downloads in src/decompnet/toolchains.toml before a user hits a dead one.

    python3 maintenance/tools/check_toolchains.py                 # shape rules, then is every URL still there? (HEAD)
    python3 maintenance/tools/check_toolchains.py --verify        # also download each file and compare its sha256
    python3 maintenance/tools/check_toolchains.py --only m2c ido-7.1 --verify

Exit code 0 when everything is fine, 1 when any rule is broken or any URL fails. Failures say what kind they are: a host
that does not resolve (`dns`, often just this machine's network), a dead link (`http`), a file that changed under its
pin (`sha`). `--verify` downloads every file, several hundred megabytes in total: run it by hand, not on every push.

The registry rules checked here (also enforced on every test run by maintenance/tests/test_maint_toolchain_check.py):
every download is https, and every one carries a 64-hex sha256. `toolchains.install` would otherwise accept an unpinned
entry and "pin it on first use", i.e. install unverified code.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import socket
import ssl
import sys
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "src" / "decompnet" / "toolchains.toml"
# Debian's salsa answers unknown agents with an anti-bot page (see install.ps1), so say who is asking
UA = "decompnet-maintenance/url-check (+https://github.com/FlyPhantomFly/Function_2_C_Decompiler)"
HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Part:
    toolchain: str
    url: str
    sha256: str


@dataclass
class Result:
    part: Part
    ok: bool
    kind: str  # ok | dns | timeout | http | tls | sha | other
    detail: str


def load_parts(path: Path = REGISTRY) -> list[Part]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return [Part(tid, p["url"], str(p.get("sha256", ""))) for tid, tc in data.items() if isinstance(tc, dict)
            for p in tc.get("parts", [])]


def structural_problems(parts: list[Part], *, allow_http: bool = False) -> list[str]:
    problems: list[str] = []
    seen: dict[str, str] = {}
    for p in parts:
        scheme = urlsplit(p.url).scheme
        if scheme != "https" and not (allow_http and scheme == "http"):
            problems.append(f"{p.toolchain}: not https: {p.url}")
        if not HEX64.fullmatch(p.sha256):
            problems.append(f"{p.toolchain}: {p.url}: sha256 missing or not 64 lowercase hex digits ({p.sha256[:20]!r})")
        if p.url in seen and seen[p.url] != p.sha256:
            problems.append(f"{p.url}: listed with two different sha256 values")
        seen.setdefault(p.url, p.sha256)
    return problems


def _request(url: str, **kw) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": UA, **kw.pop("headers", {})}, **kw)


def check_url(part: Part, *, verify: bool, timeout: float) -> Result:
    url = part.url
    try:
        if verify:
            digest, size = hashlib.sha256(), 0
            with urllib.request.urlopen(_request(url), timeout=timeout) as r:
                while chunk := r.read(1 << 20):
                    digest.update(chunk)
                    size += len(chunk)
            if digest.hexdigest() != part.sha256:
                return Result(part, False, "sha", f"sha256 is {digest.hexdigest()}, the registry pins {part.sha256}")
            return Result(part, True, "ok", f"{size} bytes, sha256 matches")
        try:
            with urllib.request.urlopen(_request(url, method="HEAD"), timeout=timeout) as r:
                return Result(part, True, "ok", f"HTTP {r.status}")
        except urllib.error.HTTPError as e:
            if e.code not in (403, 405, 501):
                raise
            # some hosts refuse HEAD: ask for the first byte instead
            with urllib.request.urlopen(_request(url, headers={"Range": "bytes=0-0"}), timeout=timeout) as r:
                return Result(part, True, "ok", f"HTTP {r.status} (HEAD refused, GET works)")
    except urllib.error.HTTPError as e:
        return Result(part, False, "http", f"HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        reason = e.reason
        kind = ("dns" if isinstance(reason, socket.gaierror) else "timeout" if isinstance(reason, (socket.timeout, TimeoutError))
                else "tls" if isinstance(reason, ssl.SSLError) else "other")
        return Result(part, False, kind, str(reason))
    except (socket.timeout, TimeoutError):
        return Result(part, False, "timeout", f"no answer in {timeout:g}s")
    except OSError as e:
        return Result(part, False, "other", str(e))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--verify", action="store_true", help="download every file and compare its sha256 (large)")
    ap.add_argument("--only", nargs="+", metavar="ID", help="only these toolchain ids")
    ap.add_argument("--timeout", type=float, default=30, help="seconds per request (default 30; --verify needs more)")
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--allow-http", action="store_true", help="(for tests) let plain http pass the https rule")
    args = ap.parse_args(argv)

    parts = load_parts(args.registry)
    if args.only:
        parts = [p for p in parts if p.toolchain in args.only]
        if not parts:
            print(f"no downloads for {args.only}")
            return 1
    problems = structural_problems(parts, allow_http=args.allow_http)
    for line in problems:
        print(f"RULE  {line}")

    unique: dict[str, Part] = {}
    for p in parts:
        unique.setdefault(p.url, p)
    timeout = max(args.timeout, 300) if args.verify else args.timeout
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda p: check_url(p, verify=args.verify, timeout=timeout), unique.values()))

    for r in results:
        host = urlsplit(r.part.url).netloc
        print(f"{'ok  ' if r.ok else 'FAIL'}  {r.part.toolchain:<18} {host:<28} {r.detail}")
    bad = [r for r in results if not r.ok]
    kinds: dict[str, int] = {}
    for r in bad:
        kinds[r.kind] = kinds.get(r.kind, 0) + 1
    print(f"\n{len(results)} unique downloads in {len({p.toolchain for p in parts})} toolchains: {len(results) - len(bad)} ok, "
          f"{len(bad)} failed" + (f" ({', '.join(f'{n} {k}' for k, n in sorted(kinds.items()))})" if bad else "")
          + f"; {len(problems)} rule violations")
    if any(r.kind == "dns" for r in bad):
        hosts = sorted({urlsplit(r.part.url).netloc for r in bad if r.kind == "dns"})
        print("did not resolve from here (check this machine's network before blaming the link): " + ", ".join(hosts))
    return 1 if bad or problems else 0


if __name__ == "__main__":
    sys.exit(main())
