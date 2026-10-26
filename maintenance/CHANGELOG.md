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
