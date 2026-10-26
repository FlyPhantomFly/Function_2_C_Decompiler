#!/usr/bin/env python3
"""Turn a pytest JUnit XML file into a Markdown summary: counts, every non-pass, and skips grouped by reason.

Usage:  uv run pytest -q -rsfE --junitxml=junit.xml
        python3 maintenance/tools/summarize_junit.py junit.xml > summary.md

This is the "test -> requirement" table from MAINTENANCE_PLAN.md Phase 0: a skipped test's reason names the tool
or platform it needs, so the grouped skip table says what to install to run more of the suite.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict


def load(path: str) -> list[dict]:
    rows = []
    for case in ET.parse(path).getroot().iter("testcase"):
        outcome, detail = "passed", ""
        for tag in ("failure", "error", "skipped"):
            node = case.find(tag)
            if node is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
                message = (node.get("message") or "").strip()
                detail = message.splitlines()[0] if message else ""
                break
        file = (case.get("classname") or "").replace(".", "/")
        rows.append({
            "id": f"{file}.py::{case.get('name')}",
            "file": file.rsplit("/", 1)[-1] + ".py",
            "outcome": outcome,
            "detail": detail,
            "time": float(case.get("time") or 0),
        })
    return rows


def render(rows: list[dict]) -> str:
    count = Counter(r["outcome"] for r in rows)
    parts = ", ".join(f"{count[k]} {k}" for k in ("passed", "failed", "error", "skipped") if count[k])
    out = [f"**{len(rows)} test items:** {parts}", ""]

    bad = [r for r in rows if r["outcome"] in ("failed", "error")]
    if bad:
        out += ["### Failed / errored", "", "| Outcome | Test | First line of the message |", "| --- | --- | --- |"]
        out += [f"| {r['outcome']} | `{r['id']}` | {r['detail'][:110].replace('|', '/')} |" for r in bad]
        out.append("")

    skipped = [r for r in rows if r["outcome"] == "skipped"]
    if skipped:
        by_reason: dict[str, list[dict]] = defaultdict(list)
        for r in skipped:
            by_reason[r["detail"].removeprefix("skipped: ").strip() or "(no reason given)"].append(r)
        out += ["### Skipped, grouped by what they need", "", "| Items | Needs / reason | Files |", "| ---: | --- | --- |"]
        for reason, items in sorted(by_reason.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            files = ", ".join(sorted({i["file"] for i in items}))
            out.append(f"| {len(items)} | {reason.replace('|', '/')} | {files} |")
        out.append("")

    slow = sorted(rows, key=lambda r: -r["time"])[:5]
    out += ["### Slowest five", "", "| Seconds | Test |", "| ---: | --- |"]
    out += [f"| {r['time']:.1f} | `{r['id']}` |" for r in slow]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.write(render(load(sys.argv[1])))
