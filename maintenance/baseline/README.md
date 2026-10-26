# Phase 0 baseline (upstream 0.10.6 code, measured for the 0.10.7 release)

Runs A to C below were made against the untouched upstream tree (git tag `upstream-0.10.6`), so they say what the code
did *before* any change by us. Runs D (0.10.18), E (0.10.22), F (0.10.29), G (0.10.31), H (0.10.34), I (0.10.39), J (0.10.41), K (0.10.43), L (0.10.45), M (0.10.49), N (0.10.52) and O (0.11.0) are the maintained code, for comparison. The raw pytest output and
JUnit XML for each run are in `raw/` exactly as captured (they contain the sandbox's absolute paths).

## The fifteen runs

| Run | State of the machine | Result (269 test items) | Summary |
| --- | --- | --- | --- |
| **A** | Fresh checkout, `uv sync --locked`, nothing else | 107 passed, 3 failed, 20 errors, 139 skipped | [summary-A.md](summary-A.md) |
| **B** | A, plus an empty `projects/demo/target/` directory | 128 passed, 1 failed, 1 error, 139 skipped | [summary-B.md](summary-B.md) |
| **C** | B, plus every free tool the tests use (below) | **218 passed, 1 failed, 50 skipped** | [summary-C.md](summary-C.md) |
| **D** | The maintained code at 0.10.18 (no code change in 0.10.19), everything C had plus `bwrap` | **310 passed, 0 failed, 55 skipped** (365 items) | [summary-D.md](summary-D.md) |
| **E** | The maintained code at 0.10.22, same machine as D | **377 passed, 0 failed, 52 skipped** (429 items) | [summary-E.md](summary-E.md) |
| **F** | The maintained code at 0.10.29, same machine | **429 passed, 0 failed, 52 skipped** (481 items) | [summary-F.md](summary-F.md) |
| **G** | The maintained code at 0.10.31, same machine | **453 passed, 0 failed, 52 skipped** (505 items) | [summary-G.md](summary-G.md) |
| **H** | The maintained code at 0.10.34, same machine | **482 passed, 0 failed, 52 skipped** (534 items) | [summary-H.md](summary-H.md) |
| **I** | The maintained code at 0.10.39, same machine | **530 passed, 0 failed, 53 skipped** (583 items) | [summary-I.md](summary-I.md) |
| **J** | The maintained code at 0.10.41, same machine | **548 passed, 0 failed, 53 skipped** (601 items) | [summary-J.md](summary-J.md) |
| **K** | The maintained code at 0.10.43, same machine | **575 passed, 0 failed, 53 skipped** (628 items) | [summary-K.md](summary-K.md) |
| **L** | The maintained code at 0.10.45, same machine, with `BUILD_WHEEL=1` | **617 passed, 0 failed, 53 skipped** (670 items) | [summary-L.md](summary-L.md) |
| **M** | The maintained code at 0.10.49, same machine, with `CHROME` and `BUILD_WHEEL=1` | **700 passed, 0 failed, 52 skipped** (752 items) | [summary-M.md](summary-M.md) |
| **N** | The maintained code at 0.10.52, same machine, with `CHROME` and `BUILD_WHEEL=1` | **777 passed, 0 failed, 52 skipped** (829 items) | [summary-N.md](summary-N.md) |
| **O** | The first release, 0.11.0 "ROMday", same machine, with `CHROME` and `BUILD_WHEEL=1` | **782 passed, 0 failed, 52 skipped** (834 items) | [summary-O.md](summary-O.md) |

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

## Run D against run C, test by test

365 items against 269: 97 new (95 pass, 2 skip for lack of PowerShell), 1 renamed (the upstream test
`test_release_update_from_github_when_decomp_wtf_is_unreachable` became `..._when_the_release_site_is_unreachable`).
**Nothing that passed in C fails in D.** The one test that failed in C (the autopilot timing flake) passes. Three tests
(`test_bridge`, two in `test_overlays`) show as skipped in D only because the run started in a tree with no built ROMs;
they pass on the next run (the order dependence described above). On a bare machine (no toolchains, no `bwrap`, `lld` or
`llvm-objcopy`, no zlib source) the same code gives 220 passed, 145 skipped, 0 failed, which is what CI's `checks` job
runs.

## Run E against run D

429 items against 365: 64 new (all pass), none dropped. **Nothing that passed in D, or in upstream's run C, fails in E**, and nothing
is marked xfail any more: the two defects the new matching-integrity tests found (0.10.20) were fixed in 0.10.21 and 0.10.22.
The bare-machine CI commands on the same code: 284 passed, 145 skipped, 0 failed.

## Run F against run E

481 items against 429: 58 new (all pass), 6 gone: exactly the six tests of the hosted-network layer deleted in 0.10.25
(two in `test_http.py`, four in `test_phase23.py`). **Nothing that passed in E, or in upstream's run C, fails in F.** The bare-machine
CI commands on the same code: 335 passed, 146 skipped, 0 failed.

## Run G against run F

505 items against 481: 24 new (the schema tests; all pass), none gone. **Nothing that passed in F, or in upstream's run C, fails in G.** The bare-machine
CI commands on the same code: 359 passed, 146 skipped, 0 failed.

## Run H against run G

534 items against 505: 29 new (the naming tests; all pass), none gone. **Nothing that passed in G, or in upstream's run C, fails in H.** The bare-machine
CI commands on the same code: 388 passed, 146 skipped, 0 failed.

## Run I against run H

583 items against 534: 49 new, none gone. **Nothing that passed in H, or in upstream's run C, fails in I.** The one new item that does not pass is
the screenshot-tool test, which needs `CHROME=<a browser>` and is skipped without it. The bare-machine CI commands on the same code: 436 passed, 147 skipped, 0 failed.

## Run J against run I

601 items against 583: 18 new (the eval-harness tests; all pass), none gone. **Nothing that passed in I, or in upstream's run C, fails in J.** The bare-machine
CI commands on the same code: 448 passed, 153 skipped, 0 failed.

## Run K against run J

628 items against 601: 27 new (the backup tests; all pass), none gone. **Nothing that passed in J, or in upstream's run C, fails in K.** The bare-machine
CI commands on the same code: 475 passed, 153 skipped, 0 failed.

## Run L against run K

670 items against 628: 43 new (the release-tool, release-workflow and issue-template tests; all pass), 1 gone (a CI guard test renamed when it was narrowed; its replacement passes). **Nothing that passed in K, or in
upstream's run C, fails in L.** Run with `BUILD_WHEEL=1`, so the real-wheel test ran; without it that test skips. The bare-machine CI commands on the same code (now including the wheel build and check):
516 passed, 154 skipped, 0 failed.

## Run M against run L

752 items against 670: 82 new (the spend, banner, backup and GUI-script tests; all pass), none gone. **Nothing that passed in L, or in upstream's run C, fails in M.** Run with a headless browser and `BUILD_WHEEL=1`
so the tests that need them ran (the screenshot tool, the banner render and the real wheel): that is why the skipped count is lower than it would otherwise be. The bare-machine CI commands on the same code, without
those switches: 597 passed, 155 skipped, 0 failed.

## Run N against run M

829 items against 752: 77 new (the run, closed-pipe and related tests; all pass), none gone. **Nothing that passed in M, or in upstream's run C, fails in N.** Run with a headless browser and `BUILD_WHEEL=1`. The bare-machine CI commands on the same
code, without those switches: 674 passed, 155 skipped, 0 failed.

## Run O against run N

834 items against 829: 5 new (the release-name tests; all pass), none gone. **Nothing that passed in N, or in upstream's run C, fails in O.** The bare-machine CI commands on the same code, without the browser and wheel switches:
679 passed, 155 skipped, 0 failed.

## What the 50 skips in run C need

See [summary-C.md](summary-C.md) for the grouped table. In short: the PS2 toolchain (`ee-gcc-2.96`), GBA
(`agbcc` and the Arm GNU toolchain), the proprietary CodeWarrior compilers (GameCube, DS), Ghidra and Java 21,
Windows/WSL, a PlayStation CHD that only the original developer has, and the demo DS ROM. The sandbox could not
reach `archive.archlinux.org`, `snapshot.debian.org`, `developer.arm.com` or `zlib.net`, so the first three groups are
not measured here. **They are your next measurement:** run `setup-test-env.sh` and the suite on the Parrot box and
compare with summary-C.

The one suspected-but-unmeasured area that mattered most was the compile sandbox. The baseline ran with `bwrap`
present, so the "no `bwrap` means no sandbox" fallback in `compiler.py` was not exercised. It was demonstrated by hand
and fixed in 0.10.11, with its own tests.

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
