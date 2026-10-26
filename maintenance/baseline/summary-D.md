**365 test items:** 310 passed, 55 skipped

### Skipped, grouped by what they need

| Items | Needs / reason | Files |
| ---: | --- | --- |
| 12 | needs CodeWarrior for DS (mwccarm, proprietary) and ds-decomp | test_ds.py, test_fork_rooms.py |
| 6 | needs agbcc, the Arm GNU toolchain and luvdis | test_gba.py |
| 5 | Windows only | test_platform.py |
| 5 | needs CodeWarrior (mwcc, proprietary) and the GameCube toolbelt | test_gc.py |
| 5 | needs agbcc and the Arm GNU toolchain | test_rom_data.py |
| 4 | needs Linux and the EE-GCC archive in the local download cache | test_wsl.py |
| 4 | needs ee-gcc-2.96 and binutils-mips to build the PS2 demo | test_ps2.py |
| 2 | needs PowerShell (pwsh) | test_maint_installers.py |
| 2 | needs Windows | test_wsl_windows.py |
| 2 | needs the PlayStation demo (projects/demo-psx) | test_overlays.py |
| 2 | needs the demo DS ROM (projects/demo-ds) | test_ds_rom_check.py |
| 1 | ee-gcc-2.96 not installed | test_period_compilers.py |
| 1 | needs Ghidra and Java 21+ | test_forks.py |
| 1 | needs a PlayStation CHD (the developer's own copy) | test_chd.py |
| 1 | needs the GameCube binutils | test_handwritten.py |
| 1 | needs the demo ROM (projects/demo-rom) and gcc-2.7.2-kmc | test_bridge.py |
| 1 | needs the ps2 toolchain and binutils-mips | test_export.py |

### Slowest five

| Seconds | Test |
| ---: | --- |
| 69.2 | `tests/test_app_engine.py::test_autopilot_matches_machine_drafts_for_free` |
| 45.3 | `tests/test_phase23.py::test_zlib_uses_per_unit_headers` |
| 19.8 | `tests/test_collab.py::test_a_crowd_in_one_room` |
| 17.6 | `tests/test_collab.py::test_members_stay_in_the_room_when_their_app_restarts` |
| 8.3 | `tests/test_export.py::test_check_records_a_function_written_outside` |
