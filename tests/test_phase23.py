"""Phase 2/3 features that remain in the core: reputation levels, hash-only projects and per-unit headers."""

import shutil

import pytest

from decompnet import policy, toolchains
from decompnet.network import Network, NetworkError
from decompnet.project import import_project

from .solutions import SOLUTIONS, WRONG_CLAMP
from .test_network import DEMO, HOST_GCC, needs_host_gcc

PROJECTS = DEMO.parent


@pytest.fixture
def net(tmp_path):
    if not HOST_GCC:
        pytest.skip(needs_host_gcc.kwargs["reason"])
    n = Network(tmp_path / "t.db")
    import_project(n.store, DEMO, log=lambda *_: None)
    return n






def web_agent(net, name="newbie"):
    """An agent that signed up from the web: untrusted, starts at the lowest reputation level (what the retired hosted
    registration page created; the app's own agents are trusted)."""
    return net.authenticate(net.register_agent(name, "web", trusted=False, origin="web", terms_accepted=True))


def test_reputation_gates_header_edits_and_budget(net, monkeypatch):
    agent = web_agent(net)
    assert policy.reputation(net.store, agent.id)["level"].name == "new"
    with pytest.raises(NetworkError, match="member"):
        net.edit_context(agent, "demo", "", "s32 x;", "add")
    assert "MATCH" in net.compile_and_diff(agent, "abs_s32", SOLUTIONS["abs_s32"])
    assert policy.reputation(net.store, agent.id)["level"].name == "member"
    assert "now v2" in net.edit_context(agent, "demo", "", "s32 entity_default_hp(s16 type);", "add proto")
    monkeypatch.setattr(policy, "LEVELS", (policy.Level("new", 0, 0, False), policy.Level("member", 1, 1, True)))
    with pytest.raises(NetworkError, match="compile budget"):
        net.compile_and_diff(agent, "clamp_s32", WRONG_CLAMP)


@needs_host_gcc
def test_hash_only_project_stores_no_code(tmp_path):
    proj = tmp_path / "hashdemo"
    shutil.copytree(DEMO, proj)
    toml = (proj / "project.toml").read_text().replace('slug = "demo"', 'slug = "hashdemo"')
    (proj / "project.toml").write_text(toml.replace("[target]", '[target]\nverification = "hash"'))
    net = Network(tmp_path / "h.db")
    import_project(net.store, proj, log=lambda *_: None)
    rows = net.store.all("SELECT target, asm, seed, fingerprint FROM functions")
    assert all(r["target"] is None and not r["asm"] and r["seed"] is None and len(r["fingerprint"]) == 64 for r in rows)
    agent = net.authenticate(net.register_agent("h"))
    assert "hash-only" in net.claim(agent, function="clamp_s32")
    assert "No match" in net.compile_and_diff(agent, "clamp_s32", WRONG_CLAMP)
    assert "MATCH" in net.compile_and_diff(agent, "clamp_s32", SOLUTIONS["clamp_s32"])




needs_n64 = pytest.mark.skipif(toolchains.installed("gcc-2.7.2-kmc") is None, reason="gcc-2.7.2-kmc not installed")




zlib_ready = (PROJECTS / "zlib-n64" / "original" / "zlib.h").exists()


@needs_n64
@pytest.mark.skipif(not zlib_ready, reason="run projects/zlib-n64/prepare.py first")
def test_zlib_uses_per_unit_headers(tmp_path):
    net = Network(tmp_path / "z.db")
    import_project(net.store, PROJECTS / "zlib-n64", log=lambda *_: None)
    assert net.store.one("SELECT COUNT(*) AS n FROM functions")["n"] == 71
    assert net._unit_contexts(net._project("zlib-n64")["id"]) >= {"deflate", "inflate", "trees"}
    with pytest.raises(NetworkError, match="pass `function`"):
        net.get_context("zlib-n64")
    assert "deflate_state" in net.get_context("zlib-n64", "fill_window")
    agent = net.authenticate(net.register_agent("z"))
    src = (PROJECTS / "zlib-n64" / "original" / "adler32.c").read_text()
    body = src[src.index("uLong ZEXPORT adler32("):]
    assert "MATCH" in net.compile_and_diff(agent, "adler32", body[: body.index("\n}\n") + 3], project="zlib-n64")


