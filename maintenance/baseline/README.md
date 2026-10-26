# Phase 0 baseline (upstream 0.10.6 code, measured for the 0.10.7 release)

Nothing in this folder was produced by the maintained code: the three runs below were made against the untouched
upstream tree (git tag `upstream-0.10.6`), so they say what the code did *before* any change by us. The raw pytest
output and JUnit XML for each run are in `raw/` exactly as captured (they contain the sandbox's absolute paths).

## The three runs

| Run | State of the machine | Result (269 test items) | Summary |
| --- | --- | --- | --- |
| **A** | Fresh checkout, `uv sync --locked`, nothing else | 107 passed, 3 failed, 20 errors, 139 skipped | [summary-A.md](summary-A.md) |
| **B** | A, plus an empty `projects/demo/target/` directory | 128 passed, 1 failed, 1 error, 139 skipped | [summary-B.md](summary-B.md) |
| **C** | B, plus every free tool the tests use (below) | **218 passed, 1 failed, 50 skipped** | [summary-C.md](summary-C.md) |

Test machine: Ubuntu 24.04 container, Python 3.12.3, uv 0.11.7, gcc 13.3, bubblewrap 0.9.0 (it does create a sandbox
in that container), lld and llvm 18.1.3. Toolchains installed through the project's own installer
(`gcc-2.7.2-kmc`, `gcc-2.7.2-psx`, `binutils-mips`, `m2c`, `objdiff-cli`; every download sha256-verified).

## Every non-pass in run A, classified

| Items | What failed | Cause | Class | Fixed in |
| ---: | --- | --- | --- | --- |
| 21 | everything built on the `projects/demo` fixture (`test_network`, `test_http`, `test_phase23`: 19 errors, 2 failures) | `projects/demo/target/` is not in a fresh checkout. `.gitignore` hides `projects/*/target/*.o`, git does not keep empty directories, and `project.import_project` runs the `gcc ... -o target/game.o` build without creating the directory. Adding only the empty directory (run B) makes all 21 pass. | **Upstream bug** | 0.10.8 |
| 1 | `test_app_server::test_the_api_agent_stays_within_a_small_local_context` | Reads a project row that exists only if the preceding, compiler-gated test imported the demo. It is missing the `@needs_demo` mark its neighbours carry. | **Test bug** (missing gate) | 0.10.9 |
| 1 | `test_forks::test_near_miss_gets_a_diff_and_release_restores_the_best` | Its fixture runs the demo fork's `configure.py`, which needs `gcc-2.7.2-kmc`. No skip gate. | **Test bug** (missing gate) | 0.10.9 |

Total 23 = 3 failed + 20 errors. None is a defect in matching, scoring or the sandbox.

## What each missing piece cost, in the order it was met going from B to C

| Missing | Effect on the suite | Class |
| --- | --- | --- |
| `gcc-2.7.2-kmc`, `ld.lld`, PSX toolchain, `binutils-mips` | 139 tests skipped (the intended behavior) | Environment |
| zlib 1.1.4 source (`projects/zlib-n64/original/`, fetched by `prepare.py` from `zlib.net`) | 42 errors and 3 failures, not skips: the demo-ROM, PSX, collab and export tests try to build and fail | Environment, **plus a missing gate** |
| `llvm-objcopy` | 32 errors and 1 failure. The demo-ROM build script calls it; the gates check only `ld.lld` | Environment, **plus an under-specified gate** |
| `m2c` | 3 failures in `test_app_engine`. One asserts the claim brief contains an m2c draft, and the next two depend on state that test builds; the autopilot test needs drafts | Environment, **plus a missing gate** |

After all of those, one failure remains:

| Test | Cause | Class |
| --- | --- | --- |
| `test_app_engine::test_autopilot_matches_machine_drafts_for_free` | Polls 600 x 0.1 s = 60 s for the autopilot to finish. Measured with the limit lifted: it finishes in **70 s** and passes. | **Flaky** (hardware speed); fixed in 0.10.9 |

## Order dependence between tests (found while regression-testing 0.10.7)

`test_bridge::test_bridge_imports_and_works` and `test_overlays` (2 tests) skip with "needs the demo ROM" / "needs the
PlayStation demo" on the **first** run in a tree that has never built them. The ROMs are built later in the run by
`test_rom` and `test_psx`, and pytest runs files alphabetically, so a second run executes the three tests that the
first run skipped. Run C was measured in a tree earlier runs had populated, which is why it shows them passing; a
first run in a clean tree gives 53 skips instead of 50. This is a property of upstream's suite, not of a change we made.

## What the 50 skips in run C need

See [summary-C.md](summary-C.md) for the grouped table. In short: the PS2 toolchain (`ee-gcc-2.96`), GBA
(`agbcc` and the Arm GNU toolchain), the proprietary CodeWarrior compilers (GameCube, DS), Ghidra and Java 21,
Windows/WSL, a PlayStation CHD that only the original developer has, and the demo DS ROM. The sandbox could not
reach `archive.archlinux.org`, `snapshot.debian.org`, `developer.arm.com` or `zlib.net`, so the first three groups are
not measured here. **They are your next measurement:** run `setup-test-env.sh` and the suite on the Parrot box and
compare with summary-C.

The one suspected-but-unmeasured area that matters most is the compile sandbox. The tests ran with `bwrap` present, so
the "no `bwrap` means no sandbox" fallback in `compiler.py` was not exercised. It gets its own test when it is fixed.

## A note on how run C got its zlib source

`zlib.net` was unreachable, so for these runs only (not in this repository) the source came from the `v1.1.4` tag of
`github.com/madler/zlib`, fed through the repository's own `prepare.py` logic with its sha256 check bypassed in a
scratch copy. The check that it was equivalent: `prepare.py` regenerates `projects/zlib-n64/include/context.h` and
`units/*.h` from that source, and `git status` showed all 14 files **byte-identical** to the committed ones. On your
machine use the real `prepare.py`, which verifies the pinned sha256.

## Reproduce

```sh
maintenance/baseline/setup-test-env.sh         # apt packages, uv sync, free toolchains, zlib source
uv run --locked pytest -q -rsfE --junitxml=junit.xml
python3 maintenance/tools/summarize_junit.py junit.xml
```
