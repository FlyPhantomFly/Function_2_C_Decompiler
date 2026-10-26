"""Make the references in an exported N64 tree symbolic, without changing what it builds. Step two of the shiftable export.

`decomp shift-audit` finds the words in the data that are absolute addresses. This turns the ones it can fully handle into symbols:

  - a jump-table entry (an address in the middle of a function), and a `.word .L<address>` (a local label that the generated linker script defines as an absolute number), get a global
    label `jtgt_<ADDRESS>` inserted in the function's assembly, right before the instruction at that address, and the word is rewritten to use it;
  - a word that is the exact start of a function becomes that function's name.

Nothing about the layout changes, so the ROM rebuilds byte for byte before and after: that is what the tests check, on the real demo, through the tree's own `build.py`. It is a preview unless
`apply` is given; it writes `shift-prep.json` listing every label and word it changed; it never rewrites a word whose label it could not place; and it leaves alone, and reports, what it does not
handle yet (pointers into data or bss, expressions, anything it cannot find). It does not touch `build.py` or the linker script.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import shiftaudit

LABEL = "jtgt_{:08X}"
VRAM_IN_COMMENT = re.compile(r"/\*\s*[0-9A-Fa-f]+\s+([0-9A-Fa-f]{8})\s+[0-9A-Fa-f]{8}\s*\*/")
MANIFEST = "shift-prep.json"
HANDLED = ("jump-table entry", "function pointer", "pinned label")


def prepare(tree: Path, apply: bool = False) -> dict:
    tree = Path(tree)
    report = shiftaudit.audit(tree)  # raises AuditError for a folder that is not an N64 export
    build = json.loads((tree / "build.json").read_text(encoding="utf-8"))
    asm_of = {f["name"]: f["asm"] for f in build["functions"] if f.get("asm")}
    texts: dict[str, list[str]] = {}

    def lines_of(function: str) -> list[str] | None:
        if function not in texts and function in asm_of:
            try:
                texts[function] = (tree / asm_of[function]).read_text(encoding="utf-8").split("\n")
            except OSError:
                return None
        return texts.get(function)

    labels: dict[tuple[str, int], dict] = {}
    words, left_alone = [], []
    for f in report["findings"]:
        if f["kind"] == "outside the image":
            continue
        base = {"file": f["file"], "line": f["line"], "value": f["value"], "kind": f["kind"]}
        if f["kind"] not in HANDLED:
            left_alone.append({**base, "reason": f"a pointer into the {'bss' if f['kind'] == 'bss pointer' else 'data'} is not handled yet"})
            continue
        function = f["function"]
        if f["kind"] == "function pointer":
            words.append({**base, "was": f["text"], "now": function})
            continue
        if function is None or (lines := lines_of(function)) is None:
            left_alone.append({**base, "reason": "it is not inside a function whose assembly could be read"})
            continue
        name = LABEL.format(f["value"])
        if any(re.match(rf"^{name}\s*:", ln) for ln in lines):
            words.append({**base, "was": f["text"], "now": name})  # the label is already there: just use it
            continue
        index = next((i for i, ln in enumerate(lines) if (m := VRAM_IN_COMMENT.search(ln)) and int(m.group(1), 16) == f["value"]), None)
        if index is None:
            left_alone.append({**base, "reason": f"there is no instruction at {f['value']:#010x} in {function}'s assembly to put a label before"})
            continue
        labels.setdefault((function, f["value"]), {"function": function, "address": f["value"], "name": name, "file": asm_of[function], "index": index})
        words.append({**base, "was": f["text"], "now": name})

    plan = {"applied": False, "labels": [{k: v for k, v in e.items() if k != "index"} for e in sorted(labels.values(), key=lambda e: (e["function"], e["address"]))],
            "words": sorted(words, key=lambda w: (w["file"], w["line"])), "left_alone": left_alone}
    if not apply or not (labels or words):
        return plan

    by_function: dict[str, list[dict]] = {}
    for entry in labels.values():
        by_function.setdefault(entry["function"], []).append(entry)
    for function, entries in by_function.items():
        lines = texts[function]
        for entry in sorted(entries, key=lambda e: e["index"], reverse=True):  # from the bottom up, so the indices stay right
            lines[entry["index"]:entry["index"]] = [f".globl {entry['name']}", f"{entry['name']}:"]
        (tree / asm_of[function]).write_text("\n".join(lines), encoding="utf-8")
    by_file: dict[str, list[dict]] = {}
    for w in words:
        by_file.setdefault(w["file"], []).append(w)
    for rel, edits in by_file.items():
        lines = (tree / rel).read_text(encoding="utf-8").split("\n")
        for w in edits:
            head, sep, tail = lines[w["line"] - 1].rpartition("*/")  # replace in the code, never in the listing comment
            lines[w["line"] - 1] = head + sep + tail.replace(w["was"], w["now"], 1)
        (tree / rel).write_text("\n".join(lines), encoding="utf-8")
    manifest_path = tree / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"version": 1, "labels": [], "words": []}
    manifest["labels"] += plan["labels"]
    manifest["words"] += [{k: w[k] for k in ("file", "line", "was", "now")} for w in plan["words"]]
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    plan["applied"] = True
    return plan
