"""Sandboxed compilation of untrusted agent-submitted C.

Agents never get to run their own compiler for anything that counts: every score and
every match is produced here, on the coordinator, with the project's pinned toolchain.

The compiler is a 1990s program fed text an AI wrote, so it only ever runs inside the sandbox (bubblewrap, Docker or
WSL). Without one, compiling is refused and the user is told how to fix it: it does NOT fall back to running the
compiler as the user. The ways around that are all explicit: DECOMP_UNSAFE_NO_SANDBOX=1, or running in the dedicated
Linux that Function_2_C_Decompiler's own installers build (a WSL distro or Docker image marked in /etc/decomp-wtf-runtime) or in any
container, where the VM is the boundary. `trusted` does not change this: it only skips the source filter (exports pass
it for matched code), and that code is still agent-written.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from . import wsl

MAX_SOURCE_BYTES = 64 * 1024
# Per-compile resource caps (address space, CPU seconds, output file size) and a global
# concurrency cap, so a hostile submission can't take the host down with it.
LIMITS = ["--as=2147483648", "--cpu=30", "--fsize=67108864"]
_SLOTS = threading.BoundedSemaphore(max(2, (os.cpu_count() or 4) - 1))

_COMMENTS_AND_STRINGS = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
_FORBIDDEN = [
    (re.compile(r"\b(__)?asm(__)?\b"), "inline assembly is not allowed: matches must come from C"),
    (re.compile(r"\b(GLOBAL_ASM|INCLUDE_ASM|INCLUDE_RODATA|NON_MATCHING)\b"), "asm-include macros are not allowed"),
    (re.compile(r"\.incbin\b"), ".incbin is not allowed"),
    (re.compile(r"__attribute__\s*\(\(\s*(section|naked)\b"), "section/naked attributes are not allowed"),
    (re.compile(r"(#\s*pragma|\b_Pragma)\b"), "pragmas are not allowed (ask the project admin to whitelist one)"),
    (re.compile(r"#\s*include\s*<"), "system includes are not allowed; everything you need is in context.h"),
]
_INCLUDE = re.compile(r'#\s*include\s*"([^"]+)"')


class SourceRejected(ValueError):
    pass


class SandboxUnavailable(RuntimeError):
    """Agent-written C may not be compiled here: there is no sandbox to compile it in."""


UNSAFE_ENV = "DECOMP_UNSAFE_NO_SANDBOX"


def check_source(source: str) -> None:
    if len(source.encode()) > MAX_SOURCE_BYTES:
        raise SourceRejected(f"source too large (max {MAX_SOURCE_BYTES} bytes)")
    for inc in _INCLUDE.findall(source):
        if inc.startswith("/") or ".." in inc.split("/"):
            raise SourceRejected(f"include path not allowed: {inc}")
    code = _COMMENTS_AND_STRINGS.sub(" ", source)
    for pattern, why in _FORBIDDEN:
        if pattern.search(code):
            raise SourceRejected(why)


@dataclass
class CompilerConfig:
    cmd: list[str]
    timeout: float = 15.0
    sandbox: str = "auto"  # auto | bwrap | docker | none
    image: str | None = None  # for sandbox = "docker"
    ro_paths: tuple[str, ...] = ()
    include_dirs: tuple[str, ...] = ()  # absolute paths of extra (static) header dirs
    runtime32: str | None = None  # 32-bit x86 C runtime for old i386 compiler binaries (see toolchains)
    wsl: bool = False  # a Linux toolchain on Windows: runs inside WSL 2, `cmd` holds WSL paths (see wsl.py)


@dataclass
class CompileResult:
    ok: bool
    obj: bytes | None
    log: str


def _unsandboxed_allowed() -> bool:
    """Someone said so (the environment variable), or this is Function_2_C_Decompiler's own Linux or a container: there the virtual
    machine is the boundary, as upstream designed it. A user's own general-purpose WSL distro is not: hostenv.runtime()
    says "wsl" for any Linux that can see Windows, so only the marker upstream's linux-base.sh writes counts."""
    if os.environ.get(UNSAFE_ENV, "").strip().lower() in ("1", "true", "yes"):
        return True
    from . import hostenv  # late: hostenv knows nothing of the compiler, keep it that way
    try:
        made = hostenv.RUNTIME_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        made = ""
    return made in ("wsl", "docker") or hostenv.runtime() == "docker"


def _sandbox_mode(cfg: CompilerConfig) -> str:
    if cfg.wsl:
        return "wsl"
    mode = cfg.sandbox
    if mode == "auto":
        mode = "bwrap" if shutil.which("bwrap") else "none"
    if mode == "none" and not _unsandboxed_allowed():
        why = 'this project asks for sandbox = "none"' if cfg.sandbox == "none" else "bubblewrap (`bwrap`) isn't installed"
        raise SandboxUnavailable(
            f"agent-written C is not compiled without a sandbox, and {why}. Install bubblewrap and try again "
            f"(Debian, Ubuntu, Parrot: `sudo apt install bubblewrap`). Only if you accept that the compiler then runs "
            f"with your user's full access, set {UNSAFE_ENV}=1.")
    return mode


def sandbox_problem() -> str:
    """Why compiling would be refused on this machine, for a warning at startup; "" when it would not."""
    if os.name == "nt":  # there the compilers run in WSL 2, which has its own checks
        return ""
    try:
        _sandbox_mode(CompilerConfig(cmd=[]))
    except SandboxUnavailable as e:
        return str(e)
    return ""


def _root(cfg: CompilerConfig, work: Path) -> str:
    """How the compiler sees the work folder (in WSL it works on a copy, see wsl.run)."""
    mode = _sandbox_mode(cfg)
    return "/work" if mode in ("bwrap", "docker") else wsl.stage_dir() if mode == "wsl" else str(work)


def _wrap(cfg: CompilerConfig, work: Path, argv: list[str]) -> list[str]:
    mode = _sandbox_mode(cfg)
    if mode in ("none", "bwrap") and shutil.which("prlimit"):
        argv = ["prlimit", *LIMITS, "--", *argv]
    if mode == "none":
        return argv
    if mode == "docker":
        if not cfg.image:
            raise RuntimeError("sandbox = 'docker' needs compiler.image")
        return ["docker", "run", "--rm", "--network", "none", "--memory", "512m", "--pids-limit", "64",
                "-v", f"{work}:/work", "-w", "/work", cfg.image, *argv]
    if mode == "bwrap":
        # /tmp first, so read-only mounts of paths that live under /tmp are not hidden by it.
        cmd = ["bwrap", "--tmpfs", "/tmp", "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib64", "/lib64",
               "--symlink", "usr/bin", "/bin", "--proc", "/proc", "--dev", "/dev"]
        if cfg.runtime32:
            # i386 binaries hardcode /lib/ld-linux.so.2; give them a private /lib with the pinned loader,
            # and point the loader at the pinned 32-bit libraries. 64-bit tools ignore those libraries.
            cmd += ["--dir", "/lib", "--ro-bind", f"{cfg.runtime32}/ld-linux.so.2", "/lib/ld-linux.so.2",
                    "--ro-bind", cfg.runtime32, "/opt/rt32", "--setenv", "LD_LIBRARY_PATH", "/opt/rt32"]
        else:
            cmd += ["--symlink", "usr/lib", "/lib"]
        for p in cfg.ro_paths:
            cmd += ["--ro-bind", p, p]
        cmd += ["--bind", str(work), "/work", "--chdir", "/work", "--unshare-all", "--die-with-parent", "--new-session"]
        return [*cmd, "--", *argv]
    raise RuntimeError(f"unknown sandbox mode {mode!r}")


def _exec(cfg: CompilerConfig, work: Path, argv: list[str], timeout: float, cwd: Path | None = None, **stage):
    """`stage`: in WSL, run on a copy in WSL's own file system (wsl.run's outputs, inputs and stage)."""
    if _sandbox_mode(cfg) == "wsl":
        return wsl.run(argv, cwd or work, timeout, **stage)
    # in the work folder, never in the app's own: KMC GCC's assembler (binutils 2.6) can't read its input when the
    # current directory is / ("Bad file descriptor"), which it is for Function_2_C_Decompiler started by a service or in Docker
    return subprocess.run(_wrap(cfg, work, argv), cwd=cwd or work, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def run_in(cfg: CompilerConfig, work: Path, argv: list[str], timeout: float = 300, *,
           inputs: list[str] | None = None, outputs: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run a toolchain command inside `work` (the sandbox's /work), e.g. to build a whole exported project.
    Paths in `argv` must be relative to `work`. In WSL, naming the files it reads (`inputs`) and writes (`outputs`)
    lets old 32-bit compilers work on a copy in WSL's own file system, which they need (see wsl.run)."""
    return _exec(cfg, Path(work), argv, timeout, cwd=Path(work),
                 **({} if outputs is None else {"inputs": inputs, "outputs": outputs}))


def compile_source(cfg: CompilerConfig, context_header: str, source: str, trusted: bool = False) -> CompileResult:
    if not trusted:
        try:
            check_source(source)
        except SourceRejected as e:
            return CompileResult(False, None, f"rejected: {e}")
    try:  # before anything is written or run: no sandbox, no compile
        _sandbox_mode(cfg)
    except SandboxUnavailable as e:
        return CompileResult(False, None, str(e))

    with tempfile.TemporaryDirectory(prefix="decompnet-") as tmp:
        work = Path(tmp)
        inc = work / "include"
        inc.mkdir()
        for d in cfg.include_dirs:
            shutil.copytree(d, inc, dirs_exist_ok=True)
        # LF on every platform: to the old GCCs a backslash before CRLF doesn't continue a line ("stray '\' in program")
        (inc / "context.h").write_text(context_header, encoding="utf-8", newline="\n")
        (work / "func.c").write_text('#include "context.h"\n#line 1 "func.c"\n' + source + "\n", encoding="utf-8",
                                     newline="\n")

        root = _root(cfg, work)
        subst = {"{src}": f"{root}/func.c", "{obj}": f"{root}/func.o", "{include}": f"{root}/include"}
        argv = [subst.get(a, a) for a in cfg.cmd]
        argv = [a.replace("{include}", subst["{include}"]) for a in argv]
        try:
            with _SLOTS:
                proc = _exec(cfg, work, argv, cfg.timeout,
                             **({"outputs": ["func.o"], "stage": root} if _sandbox_mode(cfg) == "wsl" else {}))
        except subprocess.TimeoutExpired:
            return CompileResult(False, None, f"compiler timed out after {cfg.timeout}s")
        log = (proc.stdout + proc.stderr).replace(root + "/", "")
        obj = work / "func.o"
        if proc.returncode != 0 or not obj.exists():
            return CompileResult(False, None, log[-4000:] or f"compiler exited with {proc.returncode}")
        return CompileResult(True, obj.read_bytes(), log[-2000:])
