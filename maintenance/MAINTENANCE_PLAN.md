# Maintenance and extension plan

Companion to `ARCHITECTURE.md`. Ordered by risk first, then value. Each item has a concrete "done when". Phases 0 to 2 are the takeover. Phases 3 and 4 are optional growth.

**What is done, and in which version, is recorded in `CHANGELOG.md`; that file is authoritative.** This document says what to do and why.

## Status as of 0.10.27

| Item | State | Version | What is left |
| --- | --- | --- | --- |
| Phase 0 (0.1 to 0.5) | done | 0.10.7 | Re-run on your machine for the PS2, GBA, DS, GameCube and Windows rows (the sandbox could not reach four download hosts). |
| 1.1 name, repo, domain | **partly** | 0.10.10, .14, .15, .17 | Decided: `Function_2_C_Decompiler`, `FlyPhantomFly/Function_2_C_Decompiler`. Done: updater, installers, README, app links, team-room page, plugin and its agent skill, package metadata. **Open:** the product name "decomp.wtf" in app text, on-disk names such as `.decomp.wtf.json` (file formats: rename deliberately, never by find-and-replace), and the product name in commit messages and generated text (it still says "decomp.wtf"; its links now go to this fork). |
| 1.2 updater | done | 0.10.10, .16 | It points at this fork's repository (not switched off); `auto_update` stays off; never offers a downgrade. Installs from GitHub archives over HTTPS with no signature (Phase 4). |
| 1.3 license | done | 0.10.14 | No separate `NOTICE` file; the README credits upstream. |
| 1.4 sandbox | done | 0.10.11 | A `bwrap` that is installed but cannot create a namespace fails each compile with its own error; not probed in advance. |
| 1.5 `mcp` bound, lock in CI | done | 0.10.12, .13 | |
| 1.6 CI | **written, not yet run on GitHub** | 0.10.13, .18 | Push, enable Actions, read the first runs. The `sandbox` and `toolchain-urls` jobs are `continue-on-error` until then. The plan's "green badge" is not met yet; ruff covers serious errors only (428 style findings remain). |
| 1.7 toolchain URL check | done | 0.10.18 | Run it where the four blocked hosts resolve. Does not cover `m2c` (git revision). |
| Phase 2 | **started** | 0.10.20 to .27 | Done: the matching-integrity tests (invariant 1 is now guarded), which found and fixed two real defects in the core (a hash that was not an identity, an x86 crash); the **legacy hosted-network layer, deleted** (the website, the coordinator server, signup, donated compute, the `decompnet` CLI); and `luvdis_run.py`, which now refuses a luvdis it was not written for (0.10.27). **Open:** the `except Exception` audit, schema migrations, refactors, and whether to remove the now client-less hash-only mode. Invariants 2 to 6 have only upstream's tests. Windows/WSL is frozen: the Windows installer refuses (0.10.15). |
| Phases 3 and 4 | not started | | |

**Your next steps:** (1) push this work to `main` (the updater compares against that branch; until then the app is rightly
"ahead"); (2) enable Actions and watch the first runs; (3) `sudo apt install bubblewrap`, run
`maintenance/baseline/setup-test-env.sh`, then the suite, on the Parrot box.

## Phase 0: Baseline (day 1, on your Parrot box)

Nothing else is trustworthy until this is green.

1. `git init`, commit the zip contents untouched, tag `upstream-0.10.6`. Add upstream as a remote (`i12bp8/decomp.wtf`) for reference only. *(Done in the working copy that produced 0.10.7; `maintenance/patches/` holds each later change as a patch against that tag.)*
2. `uv sync && uv run pytest -x -q 2>&1 | tee baseline.txt`.
3. Install what the tests need and re-run. `maintenance/baseline/setup-test-env.sh` does this on a Debian-based system: apt packages `bubblewrap lld llvm` (the demo-ROM build calls `llvm-objcopy`, which `lld` alone does not provide), the free toolchains `gcc-2.7.2-kmc gcc-2.7.2-psx binutils-mips m2c`, and zlib's source via `projects/zlib-n64/prepare.py`. It does not accept any proprietary compiler license; install IDO or mwcc yourself if you want those tests.
4. Record: pass / fail / skip counts, and which tests need which tool (`maintenance/tools/summarize_junit.py` builds the table from a JUnit file).
   **Done when:** a table of test to requirement exists, and every failure is classified as env, upstream bug, or flaky. *(Done in 0.10.7 for the sandbox it ran in; re-run on your Parrot box for the PS2, GBA, DS, GameCube and Windows rows.)*
5. Add `CLAUDE.md` (build, run, test, conventions, the invariants below). This lets Claude Code run the loop for you. *(Done: `maintenance/CLAUDE.md`, loaded through a one-line root `CLAUDE.md`.)*

## Phase 1: Make it safe to own (week 1)

| # | Task | Why | Done when |
| --- | --- | --- | --- |
| 1.1 | Decide the fork's **name, repo and domain**. Replace every `i12bp8/decomp.wtf` and `decomp.wtf` reference (`app/updates.py` REPO/SITE, `install.sh`, `install.ps1`, `app/cli.py --repo`, `app.js`, `index.html`, `Dockerfile`, `docker-compose.yml`, README, plugin manifests) | Installed copies currently self-update from upstream | `grep -rn "i12bp8\|decomp\.wtf"` returns only credits/license |
| 1.2 | Until a release channel exists, **disable auto-update** (default off, or point it at your repo only) | Supply-chain: a third party's code replacing yours | App never contacts a non-fork host on start |
| 1.3 | Keep MIT `LICENSE` and the Sam Wolfs notice, add yours, add a short `NOTICE`/credits | MIT requirement | Both names in LICENSE |
| 1.4 | **Sandbox fails closed.** If `bwrap` is missing, refuse to compile agent code, or require an explicit `--unsafe-no-sandbox`, and print the install hint | Silent fall-back to `none` today | Test: no bwrap leads to a clear error |
| 1.5 | Pin `mcp` to a compatible range (`>=2.3,<3`), keep `uv.lock` committed, run CI with the lock | API drift | `uv sync --locked` in CI |
| 1.6 | CI (GitHub Actions): ruff, pytest (unit subset without compilers), `compileall`, and a nightly job with compilers installed | No CI today | Green badge, nightly toolchain check |
| 1.7 | **Toolchain mirror check:** a script that HEADs every URL in `toolchains.toml` and verifies sha256 | URL rot (GitHub releases, Arch archive, Debian snapshot) | Nightly job; list of dead URLs is empty |

## Phase 2: Correctness and debt (weeks 2 to 4)

- **The legacy hosted-network layer** *(Done in 0.10.24 to 0.10.25: option (a), deleted. The import graph confirmed `app/` did not need it; `decomp toolchain` was ported first, the hosted website and redirect worker went with it, and the `api.decomp.online` defaults are gone. See ARCHITECTURE section 8. What is left: hash-only projects, which nothing can create any more, and unused tables in `store.py`.)*
- **Harden `luvdis_run.py`:** pin the luvdis version in `toolchains.toml`, assert the expected string exists before patching, and fail with a clear message otherwise. Better: upstream the fix or vendor a patched copy.
- **Exceptions:** audit the ~26 `except Exception` sites. Log with context, and re-raise anything that hides a bad match or a corrupted DB.
- **Matching-integrity tests (the heart of "everything is correct").** *(Done in 0.10.20 to 0.10.22; see the changelog.)* Add property tests for `scoring.py`:
  - identical objects score 0,
  - one-register-swap scores greater than 0 and less than a reorder,
  - relocation normalization never turns a real mismatch into 0.

  Add a regression corpus: known-matching C for the demo ROM (already in `projects/demo-rom`) must stay 0 on every release.
- **Invariants to guard with tests** (state them in `CLAUDE.md`):
  1. Score 0 is the only way a function becomes matched.
  2. Agents cannot run their own compiler for anything that counts.
  3. A header edit that breaks any earlier match is rejected.
  4. A fork edit that breaks an earlier match is rolled back, and agents never write build files or asm.
  5. Nothing is pushed upstream automatically.
  6. No ROM bytes or assembly cross a team-room connection.
- **Schema migrations:** `store.py` migrates inline. Add a `schema_version` table and a migration test from a 0.10.6 DB fixture.
- **Refactor, low priority:** split `forkengine.py` (2.4k lines) and `engine.py` (1.7k) along their existing seams (claiming, import, export, autopilot). Only with the tests green first.
- **Windows/WSL:** upstream labels it unstable. As a Linux user, freeze it (no new work) and mark it unsupported unless someone needs it.

## Phase 3: Extension candidates

Ranked by value for effort. Pick with me before building.

1. **Provider/agent robustness:** retries and backoff in the built-in API agent, cost caps per project (there is an `add_spend` hook), and a model-agnostic eval harness: run N fixed functions from the demo ROM per model and track match rate and cost. This also tells you whether prompt changes help.
2. **Platforms listed "coming":** PSP, 3DS, Switch (AArch64/Clang), PC/MSVC (x86), Xbox 360. Guides for `x86`, `aarch64` and `arm` already exist, and Ghidra drafts cover x86/AArch64. The missing parts are splitting, a pinned compiler and a judge for each. Start with whichever you actually reverse.
3. **C++ for MIPS-era platforms** (PS2 especially). The README says functions from scratch there are C only.
4. **N64 shiftable export** (README: "coming"). Lets mods grow code.
5. **Better guides:** the 20 files in `app/guide/` are the agents' knowledge base. Keep improving them from real failure notes (`add_note` data).
6. **Local-first quality of life:** resume after crash, project backup/export of the SQLite DB, a headless `decomp run --until N%` mode for Claude Code.

## Phase 4: Release and operations

- Semantic versioning starting at the fork's first release (for example `0.11.0-fork.1`). A changelog. Release wheels built by CI, with checksums published next to them.
- An update channel only after the update path is signed or checksummed. Until then, "git pull and `uv sync`" is the update story.
- An issue template that matches the app's "Copy for a bug report" output.

## Working agreement for Claude Code sessions

- One change per branch, with a test. No refactor mixed with a behavior change.
- Run `uv run pytest -x -q` before and after. Compare to `baseline.txt`.
- Do not run agents against a real commercial game's data in CI. Use `projects/demo-*` only.
- Anything touching `compiler.py`, `scoring.py`, `forks/policy.py`, `collab.py` or `toolchains.toml` gets a second look from me before merge.

## Open decisions for you

1. ~~Fork name and repo.~~ Decided: `FlyPhantomFly/Function_2_C_Decompiler`, license name PhantomThreads. The staged rebrand of the product name is still open (1.1).
2. ~~Delete or keep the legacy hosted-network code.~~ Decided: delete (done in 0.10.25).
3. Which platform or feature you want first (Phase 3 item 2 depends on what you reverse).
4. Whether this stays a private tool or is published, which affects naming, update channel and the community-norms note.
