# Changelog

Every change to this fork gets its own version and its own entry here, newest first. The rules:

- One change per version. The version is bumped with `python3 maintenance/tools/bump_version.py X.Y.Z`, which moves
  `pyproject.toml`, `src/decompnet/__init__.py` and `uv.lock` together.
- Headings are exactly `## [X.Y.Z] - YYYY-MM-DD` (the 0.10.6 anchor at the bottom says `upstream` instead of a
  date, because upstream's release date isn't recorded in the code). `maintenance/tests/test_maint_release_hygiene.py`
  fails if the newest heading is not the current version, or if the three version places disagree.
- Each entry says what changed, why, how it was verified, and anything a user must do.
- Entries are tagged **Security**, **Fix**, **Test**, **Docs**, **Tooling**, **Dependencies** or **CI**.

Versions continue upstream's 0.10.x line as plain increments: `updates.version_key` compares only the first three
numbers, so a suffix such as `-fork.1` would be ignored.

## [0.10.11] - 2026-10-21

**Security.** Agent-written C is no longer compiled outside the sandbox unless someone explicitly says so. (Plan item 1.4.)

- Before: `sandbox = "auto"` quietly became `"none"` when `bwrap` was not installed, leaving only `prlimit`. Shown live on
  the old code with `bwrap` removed: the compile ran as uid 0 and could read the host's `/etc/passwd`.
- Now, in `src/decompnet/compiler.py`: with no sandbox, `compile_source` returns a failed result and `run_in` raises
  `SandboxUnavailable`, both saying why and how to fix it (`sudo apt install bubblewrap`). Nothing is run.
  `compiler.sandbox_problem()` reports the same thing, and `decomp` prints it as a `WARNING:` at startup, before an
  agent spends tokens on compiles that cannot run.
- The ways to compile without `bwrap` are all explicit: `DECOMP_UNSAFE_NO_SANDBOX=1` (only `1`, `true` or `yes`
  count); a project that sets `sandbox = "none"` is refused the same way unless that is set; and upstream's own
  environments are left as designed, because there the machine is the boundary: a Linux marked by
  `/etc/decomp-wtf-runtime` (what upstream's `linux-base.sh` writes in its WSL distro and Docker image, which ship
  without `bwrap`) and any Docker container. A user's own general-purpose WSL distro is **not** exempt:
  `hostenv.runtime()` says "wsl" for any Linux that can see Windows, so it is not used as the signal.
- `trusted=True` does not buy a way around it. It only skips the source filter, and `export_build.py` /
  `export_gba_build.py` pass it for matched *agent-written* code. A test pins that.
- With `bwrap` present nothing changes, and the opt-out does not switch off a sandbox that is there.
- Tests: 21 new in `maintenance/tests/test_maint_sandbox.py`, including one that proves isolation (the compiler
  cannot see `/etc/passwd` inside `bwrap`, and can outside it). `tests/test_hostenv.py` simulates the marked Linux its
  docstring describes. `tests/conftest.py`: on a machine without `bwrap` the demo-code tests run with the opt-out set
  and the pytest header says so, so the suite behaves as before there.
- Verified with `bwrap` really removed: the startup banner shows the warning; through the real tool path an agent
  gets `COMPILE ERROR ... not compiled without a sandbox`; the full suite is 271 passed, 52 skipped, 0 failed. With
  `bwrap`: the compile-path test files and all maintenance tests, 94 passed.
- **Users on a machine without bubblewrap must install it**, or compiles stop. Not changed: if `bwrap` is installed but
  cannot create a namespace (some hardened kernels) every compile already fails closed with bwrap's own error, and it
  is not probed in advance; `bwrap` finds `prlimit` through the inherited `PATH`, so a `PATH` without `/usr/bin` also
  fails closed.

## [0.10.10] - 2026-10-21

**Security.** The updater reads from and installs from this fork's repository only. (Plan items 1.1 and 1.2, the
updater half.)

- Before: the updater looked at `i12bp8/decomp.wtf` and `https://decomp.wtf`, 20 seconds after launch and every 5
  minutes, on by default. An `install.json` written by upstream's installer pinned upstream's repo even if the
  constant changed. A copy of this fork would have offered to replace itself with upstream's code.
- Now, in `src/decompnet/app/updates.py`:
  - `REPO = "FlyPhantomFly/Function_2_C_Decompiler"` and `SITE = ""` (no release site yet; releases come from the
    repository's GitHub tags). An **empty `REPO` turns updates off entirely**: `check()` returns a `disabled` answer,
    nothing is contacted, `install()` and `Updater.apply()` refuse.
  - `installed()` always reports `REPO`, ignoring any repo recorded in `install.json`; `record()` never stores another.
  - `install()` refuses any package that is not under `https://github.com/<REPO>/archive/` (or `SITE/dl/` when a site is
    set), whatever `check()` produced. The version read from the network must look like a version, and a branch's
    commit id must be 40 hex characters, because both are put into the URL that gets installed.
  - The Windows and no-`uv` messages no longer tell users to run upstream's installer (`irm https://decomp.wtf/...`).
  - The `User-Agent` of the check no longer says `decomp.wtf`.
- `app/server.py`: the background watcher and the GUI endpoint honor "no update source".
  `app/cli.py`: `decomp update` says updates are off and exits 1 instead of printing "up to date"; the installers'
  `--repo` option is accepted and ignored.
- Verified: 18 new tests in `maintenance/tests/test_maint_updater.py` (16 failed before the change); the 8 tests in
  `tests/test_updates.py` were adapted to read `updates.REPO` / `updates.SITE` instead of hard-coding upstream's
  values and still pass. **Live check:** the real updater, against the real network, opens exactly one URL,
  `raw.githubusercontent.com/FlyPhantomFly/Function_2_C_Decompiler/main/site/public/install.sh`, and offers nothing
  (that file says 0.10.6, older than this build); with `REPO` empty it opens none.
- What this does not do: a copy already installed from *upstream's* installer still runs upstream's updater until it is
  replaced with this code. `site/public/install.sh`, `install.ps1` and the README's install commands still fetch
  upstream's wheel; the README and installers are a separate change. Updates stay manual-approval:
  `auto_update` is off by default and was not touched.
- Nothing for users to do. To switch updates off completely, set `REPO = ""` or `DECOMP_UPDATES=off`.

## [0.10.9] - 2026-10-21

**Test.** On a machine without the optional tools the suite now skips with a reason instead of failing or erroring.

- Measured goal: on a bare fresh clone (no toolchains, no `lld` or `llvm-objcopy`, no zlib source) the suite had
  2 failures and 1 error after 0.10.8; it now has **0 failed of 284 (143 passed, 141 skipped)**. With every free tool
  installed it is **231 passed, 53 skipped, 0 failed** (baseline C was 218 passed, 1 failed).
- New `maintenance/testgates.py`: one function, `demo_rom_problem(toolchain)`, that says what is missing for the demo
  ROM to be built (the toolchain, `ld.lld`, `llvm-objcopy`, zlib's source) and is used as the skip reason. It replaces
  the `ld.lld`-only checks in `test_rom`, `test_app_engine`, `test_collab`, `test_speed`, `test_psx` and `test_export`.
  The demo-ROM build scripts need `llvm-objcopy` and zlib's source, which the old checks never looked at.
- `test_app_server::test_the_api_agent_stays_within_a_small_local_context` gets the `@needs_demo` mark its neighbours
  have; `test_forks::test_near_miss_gets_a_diff_and_release_restores_the_best` gets `@needs_tools`;
  `test_bridge` also requires `gcc-2.7.2-kmc`, not just a leftover ROM file.
- `test_app_engine`: the "brief contains an m2c draft" assertion applies only when m2c is installed (it used to fail
  three tests in a row without it), and the autopilot test is skipped without m2c.
- The autopilot test waits up to 5 minutes instead of 60 s. It returns the moment the autopilot finishes, so fast
  machines are not slower; it takes about 70 s where it used to time out.
- Not changed: `test_bridge` and the two `test_overlays` tests still skip on the first run in a clean tree and run on
  the second (see `baseline/README.md`).
- Note: upstream's tests now import `maintenance.testgates`, so deleting `maintenance/` breaks them.
- Nothing for users to do.

## [0.10.8] - 2026-10-21

**Fix.** A fresh checkout can import the `projects/demo` project.

- `project.import_project` ran a project's `build` command (the demo's `gcc ... -o target/game.o`) without creating the
  directory the output goes in. A clone has no `projects/demo/target/` (the `.o` files are gitignored and git does not
  keep empty directories), so the first import died in gcc with "can't create target/game.o". It now creates each
  output's parent directory first, as the neighbouring `build_from` path already did. Two lines in
  `src/decompnet/project.py`.
- This was 21 of the 23 non-passing items on a fresh checkout in the Phase 0 baseline (`test_network`, `test_http`,
  `test_phase23`).
- Verified: the new `maintenance/tests/test_maint_fresh_checkout.py` fails on 0.10.7 with the gcc error above and passes
  now; `tests/test_network.py`, `tests/test_http.py` and `tests/test_phase23.py` (26 tests, 21 of them failing before)
  pass with `target/` absent.
- Nothing for users to do.

## [0.10.7] - 2026-10-21

**Docs, Tooling, Test.** No change to the application's behavior.

- Added the `maintenance/` folder, the one place for everything generated while maintaining this fork:
  `ARCHITECTURE.md`, `MAINTENANCE_PLAN.md`, `CLAUDE.md`, `README.md`, this changelog, `baseline/`, `tools/`, `tests/`
  and `patches/`. A one-line root `CLAUDE.md` points into it so Claude Code finds the instructions.
- **Phase 0 baseline recorded** in `maintenance/baseline/` (raw pytest output, JUnit files, a classified summary and
  a script to rebuild the test environment). Result on a fresh checkout: 107 passed, 3 failed, 20 errors, 139 skipped.
  With the free toolchains installed: 218 passed, 1 failed, 50 skipped. Every failure is explained there; the
  causes are fixed in the entries above this one as they land.
- Added `maintenance/tools/bump_version.py` (bumps the three version places together and refuses if they already
  disagree) and `maintenance/tools/summarize_junit.py` (turns a JUnit file into the test-to-requirement table).
- Added `maintenance/tests/test_maint_release_hygiene.py` (version agreement, changelog discipline, and the bump
  tool's refusal cases). `pyproject.toml` now lists `maintenance/tests` in pytest's `testpaths`.
- Updated the handoff documents with what running the code showed. `ARCHITECTURE.md`: the test count is 246
  functions / 269 collected items in 38 files, and section 10 now separates what was read from what was verified by
  running (findings 8 to 12) and lists what is still open. `MAINTENANCE_PLAN.md`: Phase 0 step 3 now names every
  prerequisite that proved necessary (`llvm-objcopy`, `m2c`, the zlib download), which the original omitted.

## [0.10.6] - upstream

Upstream's last release (decomp.wtf by sam wolfs, MIT). This repository is that code, untouched, plus the entries
above. The upstream notice says the project is discontinued.
