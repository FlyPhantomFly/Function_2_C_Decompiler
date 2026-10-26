"""Where the coordinator decides a function matched: the places that must refuse a forged candidate.

Three places compare a candidate with a target: `scoring.diff` (every project that stores the target), and two spots in
`network.py` for hash-only projects, where only a fingerprint and the size are kept. Each test pairs a control (the real
solution is still credited) with a forgery: a longer function with no relocations whose bytes are the target's masked
code followed by the text of its relocations, which hashes the same (see test_maint_scoring.py). The compiler is
replaced by a stand-in that hands back the forged function, because C source cannot produce such bytes: this tests the
comparison, not the compiler.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from decompnet import compiler
from decompnet.compiler import CompileResult
from decompnet.elfobj import FunctionObj, Reloc, extract_function
from decompnet.network import Network
from decompnet.project import import_project

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # `tests` is a package at the repository root; this file lives outside it
from tests.solutions import SOLUTIONS  # noqa: E402

DEMO = ROOT / "projects" / "demo"
FUNCTION = "rng_next"  # 30 bytes, two relocations, and a known solution

pytestmark = [
    pytest.mark.skipif(shutil.which("gcc") is None, reason="needs gcc to build the demo project's target"),
    pytest.mark.skipif(bool(compiler.sandbox_problem()), reason="needs bubblewrap: the demo solutions compile in the sandbox"),
]


def forge(target: FunctionObj) -> FunctionObj:
    """Longer than the target, no relocations, and the same fingerprint."""
    tail = b"".join(repr(r.key()).encode() for r in sorted(target.relocs, key=Reloc.key))
    return FunctionObj(target.name, target.arch, target.big_endian, target.normalized() + tail, [])


def make_net(tmp_path: Path, *, hash_only: bool) -> tuple[Network, Path]:
    root = tmp_path / ("hashdemo" if hash_only else "demo")
    shutil.copytree(DEMO, root, ignore=shutil.ignore_patterns("target"))
    if hash_only:
        toml = (root / "project.toml").read_text(encoding="utf-8").replace('slug = "demo"', 'slug = "hashdemo"')
        (root / "project.toml").write_text(toml.replace("[target]", '[target]\nverification = "hash"'), encoding="utf-8")
    net = Network(tmp_path / "t.db")
    import_project(net.store, root, log=lambda *_: None)
    return net, root


def target_function(root: Path) -> FunctionObj:
    target = extract_function((root / "target" / "game.o").read_bytes(), FUNCTION)
    assert target is not None and target.relocs and len(forge(target).code) > len(target.code)
    return target


def stub_compiler(net: Network, forged: FunctionObj) -> None:
    net._compile = lambda *a, **k: CompileResult(True, b"object", "")
    net._evaluate = lambda *a, **k: (forged, None, [])


def status(net: Network) -> str:
    return net.store.one("SELECT status FROM functions WHERE name=?", FUNCTION)["status"]


# ---- projects that store the target: scoring.diff decides ---------------------------------------------------------


def test_a_real_solution_is_credited(tmp_path):
    net, _ = make_net(tmp_path, hash_only=False)
    agent = net.authenticate(net.register_agent("a"))
    net.claim(agent, function=FUNCTION)
    assert "MATCH" in net.compile_and_diff(agent, FUNCTION, SOLUTIONS[FUNCTION])
    assert status(net) == "matched"


@pytest.mark.xfail(strict=True, reason="diff() trusts the fingerprint alone (fixed in the next version)")
def test_a_forged_longer_candidate_is_not_credited(tmp_path):
    net, root = make_net(tmp_path, hash_only=False)
    stub_compiler(net, forge(target_function(root)))
    agent = net.authenticate(net.register_agent("a"))
    net.claim(agent, function=FUNCTION)
    text = net.compile_and_diff(agent, FUNCTION, "int rng_next(void) { return 0; }")
    assert "MATCH" not in text and status(net) != "matched", text


# ---- hash-only projects: the stored fingerprint and size decide ---------------------------------------------------


def test_a_real_solution_is_credited_in_a_hash_only_project(tmp_path):
    net, _ = make_net(tmp_path, hash_only=True)
    agent = net.authenticate(net.register_agent("a"))
    net.claim(agent, function=FUNCTION)
    assert "MATCH" in net.compile_and_diff(agent, FUNCTION, SOLUTIONS[FUNCTION])
    assert status(net) == "matched"


@pytest.mark.xfail(strict=True, reason="the hash-only comparison trusts the fingerprint alone (fixed in the next version)")
def test_a_forged_longer_candidate_is_not_credited_in_a_hash_only_project(tmp_path):
    net, root = make_net(tmp_path, hash_only=True)
    stub_compiler(net, forge(target_function(root)))
    agent = net.authenticate(net.register_agent("a"))
    net.claim(agent, function=FUNCTION)
    text = net.compile_and_diff(agent, FUNCTION, "int rng_next(void) { return 0; }")
    assert "MATCH" not in text and status(net) != "matched", text


# ---- the re-check when a shared header changes ----------------------------------------------------------------


def _matched_row(net: Network, root: Path):
    agent = net.authenticate(net.register_agent("a"))
    net.claim(agent, function=FUNCTION)
    assert "MATCH" in net.compile_and_diff(agent, FUNCTION, SOLUTIONS[FUNCTION])
    return net._project("demo"), net.store.one("SELECT * FROM functions WHERE name=?", FUNCTION)


def test_the_header_recheck_accepts_a_function_that_still_matches(tmp_path):
    net, root = make_net(tmp_path, hash_only=False)
    proj, row = _matched_row(net, root)
    header = net._context(proj["id"], row["unit"])["header"]
    assert net.regression_test(proj, header, only=[row]) == []


@pytest.mark.xfail(strict=True, reason="the header re-check trusts the fingerprint alone (fixed in the next version)")
def test_the_header_recheck_does_not_accept_a_forged_candidate_as_still_matching(tmp_path):
    net, root = make_net(tmp_path, hash_only=False)
    proj, row = _matched_row(net, root)
    stub_compiler(net, forge(target_function(root)))
    assert net.regression_test(proj, "", only=[row]) != []
