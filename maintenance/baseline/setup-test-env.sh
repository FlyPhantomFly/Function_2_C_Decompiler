#!/usr/bin/env bash
# Rebuild the environment the 0.10.7 baseline was measured in, on Debian / Ubuntu / Parrot. Safe to re-run.
#
#   maintenance/baseline/setup-test-env.sh            # everything below
#   uv run --locked pytest -q -rsfE --junitxml=junit.xml
#   python3 maintenance/tools/summarize_junit.py junit.xml
#
# What it does NOT do: accept a proprietary compiler license (IDO, mwcc, mwccarm), or install Windows/WSL pieces.
# Those tests stay skipped until you install them yourself. Each failed step is reported, then the script goes on.
set -uo pipefail
cd "$(dirname "$0")/../.."

failed=()
step() { printf '\n== %s\n' "$1"; }
try()  { "$@" || failed+=("$*"); }

step "system packages (bubblewrap = the compile sandbox, lld + llvm = demo-ROM build, gcc/git = demo project and forks)"
if command -v apt-get >/dev/null 2>&1; then
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  try $SUDO apt-get install -y bubblewrap lld llvm gcc git
else
  echo "no apt-get here: install bubblewrap, lld, llvm (for llvm-objcopy), gcc and git with your package manager"
fi
for tool in bwrap ld.lld llvm-objcopy gcc git; do
  command -v "$tool" >/dev/null 2>&1 || failed+=("missing command: $tool")
done

step "uv and the locked Python dependencies"
if command -v uv >/dev/null 2>&1; then
  try uv sync --locked
else
  failed+=("uv is not installed (https://docs.astral.sh/uv/)")
fi

step "free toolchains the tests use (all sha256-pinned in src/decompnet/toolchains.toml)"
for tc in gcc-2.7.2-kmc gcc-2.7.2-psx binutils-mips m2c objdiff-cli; do
  try uv run --locked decompnet toolchain install "$tc"
done

step "zlib 1.1.4 source for the demo ROM (downloaded from zlib.net, checked against a pinned sha256)"
try python3 -I projects/zlib-n64/prepare.py

step "summary"
uv run --locked decompnet toolchain list 2>/dev/null | awk 'NR==1 || /installed/' || true
if [ "${#failed[@]}" -gt 0 ]; then
  printf '\nThese steps did not succeed:\n'; printf '  - %s\n' "${failed[@]}"
  echo "Tests that need them will skip or error; see maintenance/baseline/README.md."
  exit 1
fi
echo "environment ready"
