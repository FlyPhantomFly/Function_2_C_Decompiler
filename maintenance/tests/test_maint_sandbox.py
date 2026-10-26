"""Agent-written C must never be compiled outside the sandbox unless someone deliberately says so.

Upstream's `sandbox = "auto"` quietly became "none" when `bwrap` was missing, leaving only `prlimit` between a
1990s compiler and the user's account. These tests pin the replacement behavior. The "compiler" is `cp`: if it runs,
the compile succeeds, so `ok` tells us whether the sandbox rule let it through. Nothing here needs a real toolchain.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from decompnet import compiler, hostenv
from decompnet.compiler import CompilerConfig, SandboxUnavailable

SOURCE = "int f(void) { return 0; }"
REAL_WHICH = shutil.which


def cp_config(**kw) -> CompilerConfig:
    return CompilerConfig(cmd=["cp", "{src}", "{obj}"], **kw)


@pytest.fixture
def no_bwrap(monkeypatch, tmp_path):
    """A native machine without bubblewrap: no opt-out, no marked runtime, not in a container."""
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == "bwrap" else REAL_WHICH(name, *a, **k))
    monkeypatch.delenv(compiler.UNSAFE_ENV, raising=False)
    monkeypatch.setattr(hostenv, "RUNTIME_FILE", tmp_path / "no-such-runtime-file")
    monkeypatch.setattr(hostenv, "runtime", lambda: "native")


def test_without_bwrap_agent_c_is_refused_and_the_compiler_never_runs(no_bwrap):
    res = compiler.compile_source(cp_config(), "", SOURCE)
    assert res.ok is False and res.obj is None
    assert "bubblewrap" in res.log and "sudo apt install bubblewrap" in res.log and compiler.UNSAFE_ENV in res.log


def test_the_export_path_is_covered_too_trusted_only_skips_the_source_filter(no_bwrap):
    """export_build compiles matched agent C with trusted=True; that must not buy it a way around the sandbox."""
    res = compiler.compile_source(cp_config(), "", SOURCE, trusted=True)
    assert res.ok is False and "bubblewrap" in res.log


def test_run_in_refuses_too(no_bwrap, tmp_path):
    with pytest.raises(SandboxUnavailable, match="bubblewrap"):
        compiler.run_in(cp_config(), tmp_path, ["true"])


def test_a_project_that_asks_for_no_sandbox_is_refused_unless_someone_opts_out(no_bwrap):
    res = compiler.compile_source(cp_config(sandbox="none"), "", SOURCE)
    assert res.ok is False and 'sandbox = "none"' in res.log


def test_the_explicit_opt_out_lets_it_run(no_bwrap, monkeypatch):
    monkeypatch.setenv(compiler.UNSAFE_ENV, "1")
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is True
    assert compiler.compile_source(cp_config(sandbox="none"), "", SOURCE).ok is True


@pytest.mark.parametrize("value", ["", "0", "no", "false", "off", "maybe"])
def test_only_a_clear_yes_counts_as_the_opt_out(no_bwrap, monkeypatch, value):
    monkeypatch.setenv(compiler.UNSAFE_ENV, value)
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is False


@pytest.mark.parametrize("marked", ["docker", "wsl"])
def test_the_runtimes_upstream_builds_itself_are_their_own_boundary(no_bwrap, tmp_path, monkeypatch, marked):
    """linux-base.sh writes /etc/decomp-wtf-runtime in decomp.wtf's own WSL distro and Docker image, which ship without bwrap."""
    marker = tmp_path / "runtime"
    marker.write_text(marked + "\n", encoding="utf-8")
    monkeypatch.setattr(hostenv, "RUNTIME_FILE", marker)
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is True


@pytest.mark.parametrize("content", ["native", "garbage", ""])
def test_a_runtime_marker_that_does_not_say_wsl_or_docker_buys_nothing(no_bwrap, tmp_path, monkeypatch, content):
    marker = tmp_path / "runtime"
    marker.write_text(content, encoding="utf-8")
    monkeypatch.setattr(hostenv, "RUNTIME_FILE", marker)
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is False


def test_a_container_is_a_boundary(no_bwrap, monkeypatch):
    monkeypatch.setattr(hostenv, "runtime", lambda: "docker")
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is True


def test_a_users_own_wsl_distro_is_not(no_bwrap, monkeypatch):
    """hostenv.runtime() says "wsl" for any Linux that can see Windows; only upstream's marked distro is a dedicated one."""
    monkeypatch.setattr(hostenv, "runtime", lambda: "wsl")
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is False


def test_the_problem_is_reported_for_the_startup_warning(no_bwrap):
    assert "bubblewrap" in compiler.sandbox_problem()


@pytest.mark.skipif(REAL_WHICH("bwrap") is None, reason="needs bubblewrap")
def test_with_bwrap_nothing_changes_and_the_compile_really_is_isolated(monkeypatch):
    monkeypatch.delenv(compiler.UNSAFE_ENV, raising=False)
    assert compiler.sandbox_problem() == ""
    # inside the sandbox /etc isn't there; outside it, /etc/passwd is, so this only succeeds if bwrap is really used
    isolated = CompilerConfig(cmd=["sh", "-c", "test ! -e /etc/passwd && cp /work/func.c /work/func.o"])
    assert Path("/etc/passwd").exists()
    res = compiler.compile_source(isolated, "", SOURCE)
    assert res.ok is True, res.log
    assert compiler.compile_source(cp_config(), "", SOURCE).ok is True


@pytest.mark.skipif(REAL_WHICH("bwrap") is None, reason="needs bubblewrap")
def test_the_opt_out_does_not_switch_off_a_sandbox_that_is_there(monkeypatch):
    """The opt-out only matters when there is no sandbox; with bwrap installed it must still be used."""
    monkeypatch.setenv(compiler.UNSAFE_ENV, "1")
    isolated = CompilerConfig(cmd=["sh", "-c", "test ! -e /etc/passwd && cp /work/func.c /work/func.o"])
    assert compiler.compile_source(isolated, "", SOURCE).ok is True
