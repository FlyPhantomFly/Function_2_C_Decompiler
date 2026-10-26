"""What in an exported N64 tree is pinned to an absolute address, so that growing code would break it.

The export rebuilds the game byte for byte because the build it writes pins everything to its original address. A build that lets code grow (a "shiftable" one) can only work if
every reference to something that moves is a symbol the linker can resolve again, not a number. This reads a tree (`build.json` and the assembly beside it) and reports, without
changing anything:

  - in the code: address loads that are `%hi(symbol)` (movable) and `lui` with a number that looks like a RAM address (pinned); calls and jumps to a symbol (movable) and to a number (pinned);
  - in the data: words that are a symbol or label (movable), and words that are an absolute RAM address (pinned), each with what it points at: the middle of a function (a jump-table
    entry), the start of a function, data (named relative to the nearest data label before it), bss, or nothing in the program;
  - for a jump-table entry: whether the function's own assembly already has a label at the target. The disassembler often does not emit one, in which case a shiftable build has to
    insert it.

An address-like value is 0x80000000 to 0x807FFFFF; in a `lui`, a top half of 0x8000 to 0x807F. So `lui $at, 0x3F80` (the float 1.0) and hardware registers (0xA4xx) are not flagged.
What it cannot see is said in the report: overlays, compressed segments, ROM offsets kept in the game, addresses built by arithmetic.
"""

from __future__ import annotations

import bisect
import json
import re
from pathlib import Path

RAM_LO, RAM_HI = 0x80000000, 0x80800000
HI_LO, HI_HI = 0x8000, 0x807F
COMMENT = re.compile(r"/\*.*?\*/")
ROM_VRAM = re.compile(r"/\*\s*[0-9A-Fa-f]+\s+([0-9A-Fa-f]{8})\s+[0-9A-Fa-f]{8}\s*\*/")
LUI = re.compile(r"\blui\s+\$\w+\s*,\s*(\S+)\s*$")
CALL = re.compile(r"\b(jal|j)\s+(\S+)\s*$")
WORD = re.compile(r"^\s*\.word\s+(.+?)\s*$")
NUMBER = re.compile(r"^(0[xX][0-9A-Fa-f]+|\d+)$")
SYMBOL = re.compile(r"^[A-Za-z_.][\w.]*$")
DLABEL = re.compile(r"^\s*(?:dlabel|glabel)\s+(\S+)")
KINDS = ("jump-table entry", "function pointer", "data pointer", "bss pointer", "outside the image")
PLURAL = {"jump-table entry": "jump-table entries", "function pointer": "function pointers", "data pointer": "data pointers", "bss pointer": "bss pointers",
          "outside the image": "outside the program image (constants, left alone)"}


class AuditError(ValueError):
    """Something to tell the person in a sentence."""


def _plain(line: str) -> str:
    return COMMENT.sub("", line).split("#")[0].strip()


def _number(text: str) -> int:
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def audit(tree: Path) -> dict:
    tree = Path(tree)
    try:
        build = json.loads((tree / "build.json").read_text(encoding="utf-8"))
    except OSError as e:
        raise AuditError(f"{tree} has no build.json: give the folder an export wrote (`<project>/source`)") from e
    except ValueError as e:
        raise AuditError(f"{tree / 'build.json'} is not valid JSON ({e})") from e
    if build.get("platform") != "n64":
        raise AuditError(f"this audit is for N64 exports; this tree is for {build.get('platform')!r}")

    segments = {s["name"]: s for s in build.get("segments", [])}
    code_segments = [s for s in segments.values() if s.get("kind") == "code"]
    funcs = sorted((f for f in build.get("functions", []) if f.get("vram")), key=lambda f: f["vram"])
    starts = [f["vram"] for f in funcs]

    def seg_end(seg) -> int:
        return seg["vram"] + seg["end"] - seg["start"] if seg and seg.get("end") is not None else RAM_HI

    ends = []
    for i, f in enumerate(funcs):
        seg = segments.get(f.get("seg"))
        bounds = [seg_end(seg)] + ([starts[i + 1]] if i + 1 < len(funcs) else [])
        bounds += [p["vram"] for p in (seg or {}).get("pieces", []) if p["vram"] > f["vram"]]
        ends.append(min(bounds))

    code = dict.fromkeys(("symbolic_hi", "hardcoded_hi", "symbolic_calls", "hardcoded_calls", "symbolic_jumps", "hardcoded_jumps"), 0)
    function_text: dict[str, str] = {}
    unreadable = 0
    for f in funcs:
        try:
            text = (tree / f["asm"]).read_text(encoding="utf-8", errors="replace")
        except (OSError, KeyError):
            unreadable += 1
            continue
        function_text[f["name"]] = text
        for raw in text.splitlines():
            line = _plain(raw)
            if m := LUI.search(line):
                operand = m.group(1)
                if operand.startswith("%hi("):
                    code["symbolic_hi"] += 1
                elif NUMBER.match(operand) and HI_LO <= _number(operand) <= HI_HI:
                    code["hardcoded_hi"] += 1
            elif m := CALL.search(line):
                op, target = m.groups()
                kind = "calls" if op == "jal" else "jumps"
                if NUMBER.match(target):
                    code[f"hardcoded_{kind}"] += 1
                elif SYMBOL.match(target):
                    code[f"symbolic_{kind}"] += 1

    labels: dict[int, str] = {}
    data_files = sorted((tree / "asm" / "data").glob("**/*.s")) if (tree / "asm" / "data").is_dir() else []
    texts = {p: p.read_text(encoding="utf-8", errors="replace").splitlines() for p in data_files}
    for lines in texts.values():
        pending = None
        for raw in lines:
            if m := DLABEL.match(raw):
                pending = m.group(1)
            elif pending and (v := ROM_VRAM.search(raw)):
                labels[int(v.group(1), 16)] = pending
                pending = None
    label_addrs = sorted(labels)

    def locate(addr: int) -> tuple[str, str, bool | None]:
        i = bisect.bisect_right(starts, addr) - 1
        if i >= 0 and addr < ends[i]:
            name = funcs[i]["name"]
            if addr == starts[i]:
                return "function pointer", name, True
            has = bool(re.search(rf"^\s*\.?L{addr:08X}\s*:", function_text.get(name, ""), re.M | re.I))
            return "jump-table entry", f"{name}+{addr - starts[i]:#x}", has
        for seg in code_segments:
            if seg["vram"] <= addr < seg_end(seg):
                j = bisect.bisect_right(label_addrs, addr) - 1
                if j >= 0 and label_addrs[j] >= seg["vram"]:
                    off = addr - label_addrs[j]
                    return "data pointer", labels[label_addrs[j]] + (f"+{off:#x}" if off else ""), None
                return "data pointer", f"{addr:#010x}", None
            if seg.get("bss_vram") and seg["bss_vram"] <= addr < seg["bss_vram"] + (seg.get("bss_size") or 0):
                return "bss pointer", f"{addr:#010x}", None
        return "outside the image", f"{addr:#010x}", None

    data = {"symbolic_words": 0, "absolute_words": 0, "other_expressions": 0, "kinds": {}, "jump_table_entries_without_a_label": 0}
    findings = []
    for path, lines in texts.items():
        rel = path.relative_to(tree).as_posix()
        for n, raw in enumerate(lines, 1):
            m = WORD.match(_plain(raw))
            if not m:
                continue
            for operand in (o.strip() for o in m.group(1).split(",")):
                if NUMBER.match(operand):
                    value = _number(operand)
                    if not RAM_LO <= value < RAM_HI:
                        continue  # a small constant: not an address
                    kind, target, has_label = locate(value)
                    data["absolute_words"] += 1
                    data["kinds"][kind] = data["kinds"].get(kind, 0) + 1
                    if kind == "jump-table entry" and not has_label:
                        data["jump_table_entries_without_a_label"] += 1
                    findings.append({"file": rel, "line": n, "value": value, "kind": kind, "target": target, "label_at_target": has_label})
                elif SYMBOL.match(operand):
                    data["symbolic_words"] += 1
                else:
                    data["other_expressions"] += 1

    blockers = []
    if code["hardcoded_hi"]:
        blockers.append(f"{code['hardcoded_hi']} `lui` instructions load an absolute address as a number, not as %hi(symbol), so they keep pointing at the old place")
    if code["hardcoded_calls"] or code["hardcoded_jumps"]:
        blockers.append(f"{code['hardcoded_calls'] + code['hardcoded_jumps']} `jal`/`j` instructions go to an absolute number, not to a symbol")
    inside = data["absolute_words"] - data["kinds"].get("outside the image", 0)
    if inside:
        detail = ", ".join(f"{n} {PLURAL[k]}" for k, n in data["kinds"].items() if k != "outside the image")
        blockers.append(f"{inside} words in the data are absolute addresses of things inside the program ({detail})")
        if data["jump_table_entries_without_a_label"]:
            blockers.append(f"{data['jump_table_entries_without_a_label']} of the jump-table entries have no label at their target, so one has to be inserted at each")
    last_code_end = max((s["start"] + (s["end"] - s["start"]) for s in code_segments), default=0)
    raw_after = [s["name"] for s in segments.values() if s.get("kind") == "raw" and s.get("start", 0) >= last_code_end]
    not_audited = ["overlays and code loaded later", "compressed segments", "ROM offsets kept in the game itself (DMA and file tables): when code grows, what they point at moves",
                   "addresses the program builds by arithmetic, and constants that are really addresses", "the header checksums, which a changed ROM must have recomputed"]
    if raw_after:
        not_audited.append(f"the raw segment(s) after the code ({', '.join(raw_after)}): their ROM position moves when code grows, and nothing here checks what refers to it")
    return {"tree": str(tree), "platform": "n64", "functions": len(funcs), "unreadable_functions": unreadable, "code": code, "data": data, "findings": findings,
            "verdict": {"shiftable_as_exported": not blockers, "blockers": blockers, "not_audited": not_audited}}


def render(report: dict, limit: int = 10) -> str:
    c, d, v = report["code"], report["data"], report["verdict"]
    ok = lambda n: "ok" if n == 0 else "PINNED"  # noqa: E731
    lines = [f"Shiftable audit of {report['tree']} ({report['platform']}, {report['functions']} functions)", "",
             "Code (what the linker can already move, and what it cannot)",
             f"  {c['symbolic_hi']:>5}  address loads use %hi(symbol)", f"  {c['hardcoded_hi']:>5}  address loads use an absolute number            {ok(c['hardcoded_hi'])}",
             f"  {c['symbolic_calls']:>5}  calls (jal) and {c['symbolic_jumps']} jumps (j) use a symbol",
             f"  {c['hardcoded_calls'] + c['hardcoded_jumps']:>5}  calls or jumps use an absolute number              {ok(c['hardcoded_calls'] + c['hardcoded_jumps'])}", "",
             "Data", f"  {d['symbolic_words']:>5}  words use a symbol or label", f"  {d['absolute_words']:>5}  words are absolute RAM addresses" + (":" if d["absolute_words"] else "")]
    for kind in KINDS:
        if kind in d["kinds"]:
            extra = f" ({d['jump_table_entries_without_a_label']} with no label at the target)" if kind == "jump-table entry" and d["jump_table_entries_without_a_label"] else ""
            lines.append(f"          {d['kinds'][kind]} {PLURAL[kind]}{extra}")
    if d["other_expressions"]:
        lines.append(f"  {d['other_expressions']:>5}  words are expressions this audit does not classify")
    shown = [f for f in report["findings"] if f["kind"] != "outside the image"][:limit]
    if shown:
        lines += ["", f"First {len(shown)} of {len([f for f in report['findings'] if f['kind'] != 'outside the image'])}:"]
        for f in shown:
            note = "" if f["label_at_target"] in (None, True) else "  (no label there)"
            lines.append(f"  {f['file']}:{f['line']}  {f['value']:#010x}  {f['kind']} -> {f['target']}{note}")
    lines += ["", "Verdict: " + ("shiftable as exported: every reference this audit can see is a symbol." if v["shiftable_as_exported"] else "NOT shiftable as exported.")]
    lines += [f"  - {b}" for b in v["blockers"]]
    lines += ["", "Not audited:"] + [f"  - {n}" for n in v["not_audited"]]
    return "\n".join(lines)
