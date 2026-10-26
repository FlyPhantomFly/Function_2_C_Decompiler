"""Dependency bounds that the code depends on.

The app imports `mcp.server.mcpserver` and `mcp.Client`, which are the mcp 2.x API. `mcp>=2.3.0` with no ceiling would
let a fresh `pip install` (anything that ignores uv.lock) pick up a future 3.x with a different API.
"""

import importlib.metadata
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]


def _mcp_requirement() -> Requirement:
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    (found,) = [Requirement(d) for d in deps if Requirement(d).name == "mcp"]
    return found


def test_mcp_is_bounded_to_the_2x_api_the_code_uses():
    spec = _mcp_requirement().specifier
    assert spec.contains("2.3.0") and spec.contains("2.99.0")
    assert not spec.contains("3.0.0"), f"mcp is allowed to move to a major version we have not tested: {spec}"
    assert not spec.contains("1.27.0")


def test_the_installed_mcp_satisfies_it_and_has_the_api_the_app_imports():
    assert _mcp_requirement().specifier.contains(importlib.metadata.version("mcp"))
    from mcp import Client  # noqa: F401  (used by the stdio bridge tests)
    from mcp.server.mcpserver import MCPServer  # noqa: F401  (the server the app is built on)
