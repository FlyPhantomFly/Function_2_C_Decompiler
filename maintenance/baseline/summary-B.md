**269 test items:** 128 passed, 1 failed, 1 error, 139 skipped

### Failed / errored

| Outcome | Test | First line of the message |
| --- | --- | --- |
| failed | `tests/test_app_server.py::test_the_api_agent_stays_within_a_small_local_context` | TypeError: 'NoneType' object is not subscriptable |
| error | `tests/test_forks.py::test_near_miss_gets_a_diff_and_release_restores_the_best` | failed on setup with "decompnet.forks.project.ForkError: setup step failed: /home/claude/baseline/pristine/.ve |

### Skipped, grouped by what they need

| Items | Needs / reason | Files |
| ---: | --- | --- |
| 27 | needs gcc-2.7.2-kmc and ld.lld to build the demo ROM | test_app_engine.py, test_rom.py, test_speed.py |
| 20 | needs gcc-2.7.2-kmc, objdiff-cli and git | test_fork_judge.py, test_forks.py |
| 19 | needs gcc-2.7.2-kmc | test_app_server.py, test_collab.py, test_hostenv.py |
| 12 | needs CodeWarrior for DS (mwccarm, proprietary) and ds-decomp | test_ds.py, test_fork_rooms.py |
| 11 | needs gcc-2.7.2-kmc and ld.lld | test_rom_data.py |
| 6 | needs agbcc, the Arm GNU toolchain and luvdis | test_gba.py |
| 5 | Windows only | test_platform.py |
| 5 | needs CodeWarrior (mwcc, proprietary) and the GameCube toolbelt | test_gc.py |
| 4 | needs Linux and the EE-GCC archive in the local download cache | test_wsl.py |
| 4 | needs ee-gcc-2.96 and binutils-mips to build the PS2 demo | test_ps2.py |
| 4 | needs gcc-2.7.2-kmc, objdiff-cli, git, ninja | test_fork_link.py |
| 3 | needs gcc-2.7.2-psx and ld.lld to build the PS1 demo | test_psx.py |
| 2 | gcc-2.7.2-kmc not installed | test_period_compilers.py, test_phase23.py |
| 2 | needs Windows | test_wsl_windows.py |
| 2 | needs the PlayStation demo (projects/demo-psx) | test_overlays.py |
| 2 | needs the demo DS ROM (projects/demo-ds) | test_ds_rom_check.py |
| 2 | needs the n64 toolchain and binutils-mips | test_export.py |
| 1 | ee-gcc-2.96 not installed | test_period_compilers.py |
| 1 | gcc-2.7.2-kmc or m2c not installed | test_period_compilers.py |
| 1 | needs a PlayStation CHD (the developer's own copy) | test_chd.py |
| 1 | needs m2c | test_forks.py |
| 1 | needs the GameCube binutils | test_handwritten.py |
| 1 | needs the demo ROM (projects/demo-rom) | test_bridge.py |
| 1 | needs the ps2 toolchain and binutils-mips | test_export.py |
| 1 | needs the psx toolchain and binutils-mips | test_export.py |
| 1 | run projects/zlib-n64/prepare.py first | test_phase23.py |

### Slowest five

| Seconds | Test |
| ---: | --- |
| 1.6 | `tests/test_app_server.py::test_an_older_app_still_running_after_an_upgrade_is_replaced` |
| 1.4 | `tests/test_platform.py::test_stopping_an_agent_stops_what_it_started` |
| 1.1 | `tests/test_http.py::test_agent_session_over_http` |
| 0.4 | `tests/test_network.py::test_every_solution_matches` |
| 0.4 | `tests/test_http.py::test_tools_require_a_valid_token` |
