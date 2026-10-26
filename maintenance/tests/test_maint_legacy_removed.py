"""The retired hosted service stays retired.

Upstream ran decomp.wtf as a hosted network (a public coordinator, open registration behind a bot check, donated compute,
public pages, an export to a shared repository) next to the local app. This fork is the local app. These tests pin that
the hosted layer is gone and that nothing orphaned or service-shaped creeps back: every module is reachable from the app,
the `decompnet` console script is gone, `site/` holds only the installers and the container files, and no hosted-service
endpoint is left in the code.
"""

from __future__ import annotations

import ast
import importlib.util
import tomllib
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

GONE = ["cli", "server", "registration", "jobs", "public", "upstream", "local"]  # the hosted layer's modules
SITE_KEEP = {"install.sh", "install.ps1", "dev.sh", "dev.ps1", "linux-base.sh", "Dockerfile"}

# Reached by no import, on purpose: scripts the exporter copies into generated projects, a tool run as a subprocess, and
# the DS template's tools (copied into a fork). A pure import graph cannot see these, so they are listed here.
# n64crc: the exported build.py imports it when the tree uses the shifting layout (decompnet.rom.export_build is that file); the app itself never needs it
NOT_IMPORTED = {"decompnet.rom.export_build", "decompnet.rom.export_gba_build", "decompnet.rom.luvdis_run", "decompnet.rom.n64crc"}
NOT_IMPORTED_PREFIX = ("decompnet.forks.ds_template.",)


@pytest.mark.parametrize("name", GONE)
def test_the_hosted_layers_modules_are_gone(name):
    assert importlib.util.find_spec(f"decompnet.{name}") is None
    assert not (SRC / "decompnet" / f"{name}.py").exists()


def test_the_decompnet_console_script_is_gone_and_decomp_remains():
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts == {"decomp": "decompnet.app.cli:main"}


def test_site_holds_only_the_installers_and_the_container_files():
    files = {p.relative_to(ROOT / "site").as_posix() for p in (ROOT / "site").rglob("*")
             if p.is_file() and "__pycache__" not in p.parts}
    assert files == {f"public/{n}" for n in SITE_KEEP}
    assert not (ROOT / "site-redirect").exists()


def _import_graph() -> tuple[dict[str, Path], dict[str, set[str]]]:
    mods: dict[str, Path] = {}
    for p in SRC.rglob("*.py"):
        name = ".".join(p.relative_to(SRC).with_suffix("").parts)
        mods[name[: -len(".__init__")] if name.endswith(".__init__") else name] = p
    edges: dict[str, set[str]] = defaultdict(set)
    for name, p in mods.items():
        is_pkg = p.name == "__init__.py"
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                edges[name] |= {a.name for a in node.names if a.name in mods}
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = name.split(".")
                    pkg = parts if is_pkg else parts[:-1]
                    base = ".".join(pkg[: len(pkg) - (node.level - 1)] + ([node.module] if node.module else []))
                else:
                    base = node.module or ""
                if base in mods:
                    edges[name].add(base)
                edges[name] |= {f"{base}.{a.name}" for a in node.names if f"{base}.{a.name}" in mods}
        for target in list(edges[name]):  # importing a.b.c imports the packages a and a.b as well
            parts = target.split(".")
            edges[name] |= {".".join(parts[:i]) for i in range(1, len(parts)) if ".".join(parts[:i]) in mods}
    return mods, edges


def test_every_module_is_reachable_from_the_app_or_is_a_listed_script():
    mods, edges = _import_graph()
    seen: set[str] = set()
    todo = ["decompnet", *[m for m in mods if m.startswith("decompnet.app")]]
    while todo:
        m = todo.pop()
        if m not in seen and m in mods:
            seen.add(m)
            todo += edges[m]
    orphans = sorted(m for m in set(mods) - seen if m not in NOT_IMPORTED and not m.startswith(NOT_IMPORTED_PREFIX))
    assert orphans == [], f"modules nothing in the app reaches: {orphans}"
    for listed in NOT_IMPORTED:
        assert listed in mods and listed not in seen  # the allowlist must not go stale either


def test_no_hosted_service_endpoint_or_signup_machinery_is_left_in_the_code():
    needles = ["api.decomp.online", "decomp.online", "challenges.cloudflare.com", "turnstile", "siteverify", "network.sh"]
    hits = []
    for p in SRC.rglob("*.py"):
        text = p.read_text(encoding="utf-8").lower()
        hits += [f"{p.relative_to(ROOT)}: {n}" for n in needles if n in text]
    assert hits == []


def test_the_user_documentation_describes_no_hosted_service_directory():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # "Cloudflare" itself stays in the README: the team rooms' quick tunnel is a feature of the app. The website is what went.
    assert "Cloudflare Workers static assets" not in readme and "build_sim" not in readme
    assert "| `site/` |" not in readme  # the layout table no longer lists a website directory


def test_no_instruction_tells_anyone_to_run_a_deleted_command():
    """Messages an agent or a user reads must not name a subcommand of the hosted-network CLI that no longer exists."""
    import re

    deleted = re.compile(r"decompnet (serve|worker|upstream|local (asm|diff)|agent (add|revoke)|project remove|function reset|note (list|delete))")
    hits = []
    for base in ("src", "projects", "plugins", "tests", "site"):
        for p in (ROOT / base).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".md", ".sh", ".ps1", ".toml", ".json", ".js", ".html"):
                hits += [f"{p.relative_to(ROOT)}:{n}" for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
                         if deleted.search(line) and p.name != Path(__file__).name]
    for doc in ("README.md",):
        hits += [f"{doc}:{n}" for n, line in enumerate((ROOT / doc).read_text(encoding="utf-8").splitlines(), 1) if deleted.search(line)]
    assert hits == [], hits


def test_the_permuter_is_only_a_source_mutator_now():
    """Its other half was the volunteer worker of the donated-compute scheme: HTTP calls to a coordinator."""
    from decompnet import permuter

    text = Path(permuter.__file__).read_text(encoding="utf-8")
    for needle in ("urllib", "Authorization", "Bearer", "/api/", "def worker", "LocalScorer", "coordinator"):
        assert needle not in text, needle
    assert callable(permuter.mutate)
