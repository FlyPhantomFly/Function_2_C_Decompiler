#!/usr/bin/env python3
"""Evaluate a model, or a prompt change, on the bundled demo ROM: how many of a fixed set of functions it matches, and what that costs.

    # a real model, through any OpenAI-compatible API (the key is read from the environment, never from the command line):
    EVAL_API_KEY=sk-... uv run python maintenance/tools/eval_agent.py --base-url https://openrouter.ai/api/v1 --model some/model \\
        --functions 10 --max-steps 40 --max-usd 2 --out results/some-model.json

    # the harness checking itself: a scripted "oracle" model that knows two answers. No key, no network. Exit code 1 if it does not match them.
    uv run python maintenance/tools/eval_agent.py --oracle

    # did a change help? (two result files from the same function set)
    uv run python maintenance/tools/eval_agent.py --compare before.json after.json

How it measures. The demo ROM's functions are mostly matched for free by the autopilot (machine drafts from m2c), so a model's skill only
shows on what the autopilot cannot do. The harness imports the demo into a throwaway home, runs the autopilot (the "free baseline", reported
beside the result), then takes the first N still-open functions in a fixed order (smallest first, then by name) and gives each to the model in a
fresh session that is told to work on that one function only. It records, per function: matched or not, tool steps, tokens, dollars (when the
provider reports a cost), seconds and any error. `--max-usd` is a hard cap: once the project's spend reaches it, the remaining functions are
skipped and reported as skipped, not as failures.

What a result is and is not. It is one run: models are not deterministic, so compare means over repeated runs before believing a small
difference. The function order is fixed by the ROM, the compiler and m2c, so two runs on the same toolchain see the same functions; a result
file says which. Nothing is sent anywhere except to the endpoint you name, and the key is never written to the result file.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "src" / "decompnet" / "app" / "static" / "demo" / "demo-quest-64.z64"
SLUG = "demo-quest-64"

# Known-matching answers for two of the demo ROM's functions (the same ones the engine and server tests match by hand). The oracle model
# knows exactly these, so a run of it that does not match them means the harness is broken, not the model.
ABS = "s32 func_800007F4(s32 v) { return v < 0 ? -v : v; }"
DAMAGE = """typedef struct {
    u8 ent[0x1C];
    s32 hp;
    s16 invuln_timer;
    s16 state;
    s32 combo;
} Player;
extern Player D_8004AE34;

void func_80000808(s32 amount) {
    if (D_8004AE34.invuln_timer > 0) {
        return;
    }
    D_8004AE34.hp -= amount;
    if (D_8004AE34.hp <= 0) {
        D_8004AE34.hp = 0;
        D_8004AE34.state = 3;
    }
    D_8004AE34.invuln_timer = 60;
}"""
ORACLE = {"func_800007F4": ABS, "func_80000808": DAMAGE}
FOCUS = re.compile(r"work only on `(\w+)`", re.IGNORECASE)  # focus_text writes it with a capital W


# ---- the pure parts: tested without a ROM, a compiler or a network --------------------------------------------------------------------------


def focus_text(name: str) -> str:
    return f"\n\nThis is an evaluation. Work only on `{name}`: claim it, match it byte for byte, and stop. Do not claim or touch any other function.\n"


def order_open(rows) -> list[str]:
    """Open functions in the fixed evaluation order: smallest first, then by name. (size may be missing: sorted as 0.)"""
    return [r["name"] for r in sorted(rows, key=lambda r: (r["size"] or 0, r["name"]))]


def oracle_reply(messages: list[dict]) -> dict:
    """What the scripted model says next, given the conversation so far: claim, compile the known answer, say it is done. A function it has no
    answer for gets an honest 'I don't know', which the harness must score as a miss."""
    text = " ".join(str(m.get("content") or "") for m in messages)
    found = FOCUS.search(text)
    name = found.group(1) if found else ""
    answered = sum(1 for m in messages if m.get("role") == "tool")

    def call(i: str, tool: str, args: dict) -> dict:
        return {"tool_calls": [{"id": i, "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]}

    if name not in ORACLE:
        return {"content": "I don't know this one."}
    if answered == 0:
        return call("1", "claim_function", {"function": name})
    if answered == 1:
        return call("2", "compile_and_diff", {"function": name, "source": ORACLE[name]})
    return {"content": "Matched."}


def summarize(rows: list[dict]) -> dict:
    done = [r for r in rows if not r.get("skipped")]
    matched = sum(1 for r in done if r["matched"])
    usd, tokens = sum(r.get("usd", 0.0) for r in done), sum(r.get("tokens", 0) for r in done)
    return {"attempted": len(done), "matched": matched, "skipped": len(rows) - len(done),
            "rate": round(matched / len(done), 3) if done else 0.0, "tokens": tokens, "usd": round(usd, 4),
            "usd_per_match": round(usd / matched, 4) if matched and usd else None,
            "mean_steps": round(sum(r.get("steps", 0) for r in done) / len(done), 1) if done else 0.0,
            "seconds": round(sum(r.get("seconds", 0.0) for r in done), 1)}


def build_report(*, model: str, base_url: str, oracle: bool, max_steps: int, free: dict, rows: list[dict], version: str) -> dict:
    """The result file. Holds the endpoint's host name and never its key."""
    return {"harness": "eval_agent", "version": version, "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "model": model, "endpoint": urlparse(base_url).hostname or "", "oracle": oracle, "max_steps": max_steps,
            "free_baseline": free, "functions": [r["function"] for r in rows], "results": rows, "summary": summarize(rows)}


def compare(a: dict, b: dict) -> str:
    """What changed between two result files: the headline numbers, and which functions were gained or lost."""
    sa, sb = a["summary"], b["summary"]
    lines = [f"A: {a['model']} ({a['date'][:10]})  ->  B: {b['model']} ({b['date'][:10]})",
             f"matched   {sa['matched']}/{sa['attempted']}  ->  {sb['matched']}/{sb['attempted']}  ({sb['matched'] - sa['matched']:+d})",
             f"tokens    {sa['tokens']}  ->  {sb['tokens']}", f"dollars   {sa['usd']}  ->  {sb['usd']}",
             f"steps/fn  {sa['mean_steps']}  ->  {sb['mean_steps']}"]
    ra, rb = {r["function"]: r for r in a["results"]}, {r["function"]: r for r in b["results"]}
    both = [f for f in ra if f in rb]
    gained = [f for f in both if rb[f]["matched"] and not ra[f]["matched"]]
    lost = [f for f in both if ra[f]["matched"] and not rb[f]["matched"]]
    lines.append(f"gained    {', '.join(gained) or 'none'}")
    lines.append(f"lost      {', '.join(lost) or 'none'}")
    if set(ra) != set(rb):
        lines.append(f"NOTE: the function sets differ ({len(set(ra) ^ set(rb))} functions are in only one file): the headline numbers are not comparable")
    return "\n".join(lines)


def render(report: dict) -> str:
    s, free = report["summary"], report["free_baseline"]
    out = [f"model {report['model']} via {report['endpoint'] or '(scripted)'}   harness {report['version']}   {report['date']}",
           (f"free baseline: the autopilot matched {free['matched']} of {free['functions']} functions before the model started" if free.get("autopilot")
            else "free baseline: not measured (the autopilot was skipped)"),
           "", f"{'function':16s} {'result':8s} {'steps':>5s} {'tokens':>8s} {'usd':>8s} {'sec':>6s}  note"]
    for r in report["results"]:
        result = "skipped" if r.get("skipped") else ("MATCH" if r["matched"] else "-")
        out.append(f"{r['function']:16s} {result:8s} {r.get('steps', 0):5d} {r.get('tokens', 0):8d} {r.get('usd', 0.0):8.4f} {r.get('seconds', 0.0):6.1f}  "
                   f"{(r.get('skipped') or r.get('error') or '')[:60]}")
    out += ["", f"matched {s['matched']} of {s['attempted']} attempted ({s['rate']:.0%})" + (f", {s['skipped']} skipped" if s["skipped"] else "")
            + f"   tokens {s['tokens']}   dollars {s['usd']}" + (f"   per match {s['usd_per_match']}" if s["usd_per_match"] else "")]
    return "\n".join(out)


# ---- the run ------------------------------------------------------------------------------------------------------------------------------------


def problem() -> str:
    """Why the demo cannot be worked on here, in words; empty when it can."""
    sys.path.insert(0, str(ROOT / "src"))
    from decompnet import compiler, toolchains

    missing = [t for t in ("gcc-2.7.2-kmc",) if toolchains.installed(t) is None] + [t for t in ("ld.lld",) if not shutil.which(t)]
    if missing:
        return f"needs {', '.join(missing)} (decomp toolchain install gcc-2.7.2-kmc)"
    return compiler.sandbox_problem()


def run_one(manager, net, slug: str, name: str, options: dict, index: int, agents) -> dict:
    if (cap := manager.over_budget(slug)) is not None:
        return {"function": name, "matched": False, "skipped": f"the ${cap:g} cap was reached"}
    agent_name = f"eval-{index}"
    session = agents.Session(f"eval-{index}", "api", f"Eval {name}", slug, agent_name, dict(options))
    agent, _ = net.local_agent(agent_name)
    original = manager.prompt
    manager.prompt = lambda sess: original(sess) + focus_text(name)  # one function per session, so the result is per function
    started, error = time.time(), ""
    try:
        manager._run_api(session, agent)
    except Exception as e:  # a harness records a crash against the function and goes on to the next
        error = f"{type(e).__name__}: {e}"
    finally:
        manager.prompt = original
    try:
        net.release(agent, name, "evaluation over")
    except Exception:  # nothing held (it matched, or was never claimed): nothing to release
        pass
    return {"function": name, "matched": net._function(name, slug)["status"] == "matched",
            "steps": sum(1 for f in session.feed if f["type"] == "tool"), "tokens": session.tokens, "usd": round(session.usd, 6),
            "seconds": round(time.time() - started, 1), "error": error or session.error}


def evaluate(args) -> int:
    reason = problem()
    if reason:
        print(f"cannot run here: {reason}", file=sys.stderr)
        return 2
    import httpx

    from decompnet import __version__
    from decompnet.app import agents

    with contextlib.ExitStack() as stack:
        if args.oracle:
            # a scripted model in place of the network, for exactly the length of this run: httpx is a shared module, so a patch that
            # outlived the run would wrap itself the next time the harness is called in the same process
            real = httpx.Client
            stack.enter_context(mock.patch.object(agents.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(oracle_transport), **kw)))
            options = {"base_url": "http://8.8.8.8/v1", "model": "oracle", "api_key": "oracle", "max_steps": args.max_steps}
        else:
            options = {"base_url": args.base_url, "model": args.model, "api_key": os.environ.get(args.api_key_env, ""), "max_steps": args.max_steps}
            if args.context_tokens:
                options["context_tokens"] = args.context_tokens
        measured = measure(args, options, agents)
    if isinstance(measured, int):
        return measured
    free, rows = measured
    report = build_report(model=options["model"], base_url="" if args.oracle else args.base_url, oracle=args.oracle, max_steps=args.max_steps,
                          free=free, rows=rows, version=__version__)
    print(render(report))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    if args.oracle and any(not r["matched"] and not r.get("skipped") for r in rows if r["function"] in ORACLE):  # a skipped one is not a miss
        print("the oracle did not match what it knows: the HARNESS is broken, not a model", file=sys.stderr)
        return 1
    return 0


def oracle_transport(request):
    """The scripted model as an HTTP server: answers the model's questions, and 404s the context-window probe a local server would get."""
    import httpx

    if request.method == "GET":
        return httpx.Response(404)
    reply = oracle_reply(json.loads(request.content)["messages"])
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None} | reply}],
                                     "usage": {"total_tokens": 100, "cost": 0.001}})


def measure(args, options: dict, agents):
    """Import the demo into a throwaway home, take the free baseline, and run the model on each chosen function. Returns (baseline, rows),
    or an exit code when the request cannot be met."""
    from decompnet.app.engine import RomNetwork

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".decomp").mkdir()
        net = RomNetwork(home / ".decomp" / "decomp.db", home)
        net.import_rom(DEMO.read_bytes(), confirmed=True, name=DEMO.name, log=lambda *_: None)
        total = net.overview(SLUG)["functions"]
        free = {"autopilot": False, "matched": 0, "functions": total}
        if not args.no_autopilot:
            print("running the autopilot for the free baseline (about a minute)...", file=sys.stderr)
            net.start_autopilot(SLUG)
            deadline = time.time() + 900
            while time.time() < deadline and (net.autopilot_status(SLUG) or {}).get("state") == "running":
                time.sleep(0.5)
            free = {"autopilot": True, "matched": (net.autopilot_status(SLUG) or {}).get("matched", 0), "functions": total}
        manager = agents.Manager(net, home / ".decomp", "http://127.0.0.1:9/mcp")
        manager.budget = lambda: float(args.max_usd or 0)
        openn = order_open(net.store.all("SELECT f.name, f.size FROM functions f JOIN projects p ON p.id=f.project_id "
                                         "WHERE p.slug=? AND f.status='open'", SLUG))
        if args.names:
            names = [n.strip() for n in args.names.split(",") if n.strip()]
        elif args.oracle and args.functions is None:
            names = list(ORACLE)
        else:
            names = openn[:args.functions or 10]
        unknown = [n for n in names if n not in openn]
        if unknown:
            print(f"not open functions of the demo: {', '.join(unknown)}", file=sys.stderr)
            return 2
        rows = []
        for i, name in enumerate(names, 1):
            row = run_one(manager, net, SLUG, name, options, i, agents)
            rows.append(row)
            print(f"[{i}/{len(names)}] {name}: {'MATCH' if row['matched'] else row.get('skipped') or 'no match'}", file=sys.stderr)
    return free, rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Evaluate a model on the demo ROM (see this file's docstring).", allow_abbrev=False)
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE.json", "AFTER.json"), help="compare two result files and exit")
    ap.add_argument("--oracle", action="store_true", help="a scripted model that knows two answers: checks the harness (no key, no network)")
    ap.add_argument("--base-url", help="an OpenAI-compatible API, e.g. https://openrouter.ai/api/v1")
    ap.add_argument("--model", help="the model name that API expects")
    ap.add_argument("--api-key", help=argparse.SUPPRESS)  # refused below: it would sit in shell history
    ap.add_argument("--api-key-env", default="EVAL_API_KEY", help="the environment variable holding the key (default EVAL_API_KEY)")
    ap.add_argument("--functions", type=int, default=None, help="how many open functions to try (default 10; with --oracle, its two)")
    ap.add_argument("--names", help="comma-separated function names instead of the first N")
    ap.add_argument("--max-steps", type=int, default=40, help="tool steps per function (default 40)")
    ap.add_argument("--max-usd", type=float, default=0.0, help="stop starting new functions once the spend reaches this (needs a provider that reports cost)")
    ap.add_argument("--context-tokens", type=int, default=0, help="the model's context size, if it cannot be found out")
    ap.add_argument("--no-autopilot", action="store_true", help="skip the free baseline (the open set then includes what the autopilot would match)")
    ap.add_argument("--out", help="write the result as JSON here")
    args = ap.parse_args(argv)
    if args.api_key is not None:
        ap.error("do not pass a key on the command line (shell history keeps it): set EVAL_API_KEY in the environment instead")
    if args.compare:
        a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in args.compare)
        print(compare(a, b))
        return 0
    if args.oracle:
        args.no_autopilot = True  # the oracle's two functions are open in the raw import
    elif not (args.base_url and args.model):
        ap.error("give --base-url and --model (or --oracle to check the harness, or --compare A B)")
    elif not os.environ.get(args.api_key_env) and not re.match(r"^https?://(127\.|localhost|\[::1\])", args.base_url):
        ap.error(f"no key: set {args.api_key_env} in the environment (not on the command line, where shell history keeps it)")
    return evaluate(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
