"""A broad `except Exception` must never make a bug invisible.

The audit of the inherited code found 30 broad handlers. None sits on a path that can produce a false match (the judging and
matching code, `scoring`, `network`, `match`, has none), but thirteen swallowed the error without a trace, so a real bug in them
would have shown only as quiet worse behavior. For example the autopilot would have turned the x86 crash fixed in 0.10.22 into a
silent "fail" on every function. The policy, enforced here for the whole source tree: a broad handler must

  1. re-raise, or
  2. use the exception (report it to the GUI, return it as text), or
  3. log (a logger call, `print`, or pushing to the agent's feed), or
  4. be on ALLOWED_SILENT below, each with the reason it is safe to say nothing.

The one that logs goes to the "decomp.wtf" logger, which the app writes to its log file.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "decompnet"
LOG_CALLS = {"debug", "info", "warning", "error", "exception", "critical", "print", "push", "log", "_log"}

# (file relative to src/decompnet) :: enclosing function :: n-th silent handler in it  ->  why saying nothing is right
ALLOWED_SILENT = {
    "app/agents.py::Manager._run#0": "link.sync() while waiting for a room's host: a network blip; the status line already says the host is unreachable",
    "app/agents.py::Manager._run#1": "best-effort release of the claim in a room as an agent stops; the host expires claims anyway",
    "forks/literals.py::mismatches#0": "an unusual object: no verdict rather than a wrong one (designed to fail safe)",
    "hostenv.py::open_url#0": "no browser at all, as on a server: open_url returns False and the caller prints the address",
}


def _handlers():
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        seen: dict[str, int] = {}
        for node in sorted((n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)), key=lambda n: n.lineno):
            if node.type is None or ast.unparse(node.type) not in ("Exception", "BaseException"):
                continue
            names, cur = [], node
            while cur in parents:
                cur = parents[cur]
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(cur.name)
            where = f"{path.relative_to(SRC).as_posix()}::{'.'.join(reversed(names))}"
            yield where, node, seen


def _kind(handler: ast.ExceptHandler) -> str:
    if any(isinstance(n, ast.Raise) for n in ast.walk(handler)):
        return "reraises"
    if handler.name and any(isinstance(n, ast.Name) and n.id == handler.name for stmt in handler.body for n in ast.walk(stmt)):
        return "uses-the-exception"
    for stmt in handler.body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Call):
                f = n.func
                if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")) in LOG_CALLS:
                    return "logs"
    return "silent"


def test_no_broad_handler_is_silent_unless_it_is_listed_with_a_reason():
    silent, counts = [], {}
    for where, node, _ in _handlers():
        if _kind(node) == "silent":
            n = counts[where] = counts.get(where, -1) + 1
            silent.append(f"{where}#{n}")
    unlisted = [s for s in silent if s not in ALLOWED_SILENT]
    assert unlisted == [], f"broad handlers that make a bug invisible (log them, re-raise, or list them with a reason): {unlisted}"
    stale = sorted(set(ALLOWED_SILENT) - set(silent))
    assert stale == [], f"allowlist entries that no longer match a silent handler (delete them): {stale}"


def test_the_matching_and_judging_code_has_no_broad_handlers_at_all():
    """The code that decides a match must let an unexpected error surface, never turn it into an answer."""
    for name in ("scoring.py", "elfobj.py", "network.py", "compiler.py", "project.py", "rom/match.py", "rom/match_arm.py"):
        text = (SRC / name).read_text(encoding="utf-8")
        assert "except Exception" not in text and "except BaseException" not in text, name


def test_the_database_wrapper_rolls_back_and_re_raises():
    text = (SRC / "store.py").read_text(encoding="utf-8")
    assert "ROLLBACK" in text and "raise" in text[text.index("ROLLBACK"):text.index("ROLLBACK") + 80]


# ---- the swallowed errors now leave a trace ---------------------------------------------------------------------------


@pytest.fixture
def seen(caplog):
    """Capture the app's logger even when another test has pointed it at a file and stopped it propagating."""
    logger = logging.getLogger("decomp.wtf")
    old = logger.propagate
    logger.propagate = True
    caplog.set_level(logging.INFO, logger="decomp.wtf")
    yield caplog
    logger.propagate = old


def _boom(*args, **kwargs):
    raise RuntimeError("the twins index is broken")


def test_a_failing_twin_lookup_still_gives_an_empty_hint_but_leaves_a_traceback(tmp_path, seen):
    from decompnet.app.engine import RomNetwork

    net = RomNetwork(tmp_path / "t.db", tmp_path)
    net.twins = SimpleNamespace(twin_of=_boom)
    assert net._twin_lines({"id": 1}, {"id": 2}) == []  # behavior unchanged: no hint
    assert any(r.levelno >= logging.WARNING and r.exc_info for r in seen.records), seen.text
    assert "the twins index is broken" in seen.text


def test_a_failing_fork_twin_lookup_still_gives_an_empty_hint_but_leaves_a_traceback(seen):
    from decompnet.app.forkengine import ForkEngine

    engine = ForkEngine.__new__(ForkEngine)
    engine.net = SimpleNamespace(twins=SimpleNamespace(twin_of=_boom))
    assert engine._twin_brief({"id": 1}, {"id": 2}) == []
    assert any(r.levelno >= logging.WARNING and r.exc_info for r in seen.records), seen.text
    assert "the twins index is broken" in seen.text
