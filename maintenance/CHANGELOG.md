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

## [0.10.33] - 2026-10-21

**Docs.** The hash-only mode is recorded as no longer functional. The owner decided to leave it in place. No behavior change.

- Decision (owner): leave hash-only projects where they are, and note that they no longer work as a feature. They were the contributor
  side of the retired hosted network (the coordinator kept a one-way fingerprint and the contributor worked against their own copy
  with client tools); those tools were deleted in 0.10.25, and nothing in the app creates or serves such a project.
- A comment on `Network._hash_only` says so where a maintainer will meet it. `ARCHITECTURE.md` section 8 and the plan record the
  decision. The code paths and their tests stay (the 0.10.21 matching-integrity fixes cover them), and so does the unused
  `registrations` and `jobs` schema in `store.py`.
- Nothing for users to do.

## [0.10.32] - 2026-10-21

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run G** in `maintenance/baseline/`: the maintained code at 0.10.31, measured the same way: **453 passed, 0 failed, 52 skipped
  (505 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run F fails; against F,
  24 items are new (the schema tests, all pass) and none is gone. The bare-machine CI commands: 359 passed, 146 skipped, 0 failed in 15 s.
- `MAINTENANCE_PLAN.md`: status as of this version. Phase 2 now also includes the schema versioning; what is left is refactors (only with
  coverage, and only if you want them) and your decision on the hash-only mode. `CLAUDE.md`: do not change the database format without
  raising `SCHEMA_VERSION` and a test from the version before.
- `maintenance/patches/`: regenerated, 26 patches (0.10.7 to 0.10.32).
- Nothing for users to do.

## [0.10.31] - 2026-10-21

**Fix, Test.** The database format is versioned, an old database is backed up before its first migration, and a database from a
newer version is refused untouched. (Plan Phase 2: schema migrations.) Touches `src/decompnet/store.py` and one `try` in
`src/decompnet/app/cli.py`; the migration steps themselves are unchanged and only moved into `Store._migrate`.

- The problem: upstream wrote `PRAGMA user_version` = 0 into every database and migrated by adding columns in place. Code therefore
  could not tell a database written by a newer version from one it knew, and **opened it anyway and rewrote its file**
  (shown by hand with the previous `store.py`: a version-99 database opened without complaint and the file changed). And the first
  migration of an old database runs `UPDATE` and `DELETE` statements on real work with no copy kept.
- Now: `SCHEMA_VERSION = 1` (0 = never stamped: upstream, or this fork before this version). **A newer database is refused before
  anything touches the file** (switching to WAL rewrites the header, so the check comes first) with "was written by a newer
  decomp.wtf: its database format is version N, and this one understands up to 1. Update decomp.wtf, or use a different database.
  The file has not been touched." The file is byte for byte unchanged, with no `-wal`, `-shm` or backup beside it. `decomp` shows that
  as one `error:` line and exits 1, not a traceback.
- **An older database is copied first**, to `<file>.bak-v<its version>` (so `decomp.db.bak-v0`) in the same folder, using SQLite's
  backup API (a consistent snapshot even mid-write), written under a temporary name and renamed so a copy that dies midway never
  looks complete. An existing backup is never overwritten. A new or empty database gets none. The copy holds exactly the same rows
  (not the same bytes: the backup API rewrites pages); restoring it is renaming it back, and it opens. **It is as large as the
  database, once; delete it when you are satisfied.**
- Migrations are unchanged and still repeatable, so one cut short finishes on the next open (tested).
- Fixture: `maintenance/tests/fixtures/db-0.10.6.sqlite`, a **real database written by upstream 0.10.6's own code** (the untouched
  `upstream-0.10.6` tree: 13 functions, 1 matched, an agent, attempts, notes, events, two header versions; `user_version` 0), with the
  generator and instructions beside it. No personal data.
- Tests: 24 in `maintenance/tests/test_maint_schema.py`. An upstream database opens, migrates and **keeps every row and column it
  had**; the backup is complete, passes `integrity_check` and restores; a failed backup stops the migration and leaves nothing that
  looks complete; each of the **eleven column migrations** works on a table that already holds rows and gives existing rows their
  default; the one-time recount of `abandons` runs once and is not repeated; a half-finished migration completes; and the app, through
  the real `Network` class, can register an agent against the migrated upstream database and claim a function, with the function upstream
  matched still matched. Verified by hand: the real `decomp` command against a version-42 database prints the error and exits 1.
  **Whole suite with every tool: 449 passed and the changelog test this entry satisfies, 0 failed**; test by test, nothing dropped, the 24
  new tests pass, and nothing regressed (three tests show as skipped only because the run started from a cleaned tree).
- **Reversible, verified:** a database stamped by this version opens and works in upstream's own 0.10.6 (it does not read the version).
- One thing you will notice: the first time an existing database is opened, `decomp.db.bak-v0` appears beside it in `~/Decomp/.decomp/`.
- Not covered: two programs opening an old database at the same instant during its first migration (not a case this app creates).
- Nothing for users to do.

## [0.10.30] - 2026-10-21

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run F** in `maintenance/baseline/`: the maintained code at 0.10.29, measured the same way: **429 passed, 0 failed, 52 skipped
  (481 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run E fails;
  against E, 58 items are new (all pass) and 6 are gone, exactly the six legacy tests deleted in 0.10.25. The bare-machine CI
  commands: 335 passed, 146 skipped, 0 failed in 13 s; `actionlint` on the workflow: clean.
- `MAINTENANCE_PLAN.md`: status as of this version (Phase 2 now includes the matching-integrity tests, the legacy-layer deletion,
  the luvdis guard and the exception audit; still open: schema migrations, refactors, and your decision on the now client-less
  hash-only mode). `CLAUDE.md`: two more things not to do (a silent broad `except`, an unreachable module), each with the test
  that fails.
- `maintenance/patches/`: regenerated, 24 patches (0.10.7 to 0.10.30).
- Nothing for users to do.

## [0.10.29] - 2026-10-21

**Fix, Test.** No broad `except` can make a bug invisible any more. The audit of the inherited `except Exception` sites (plan
Phase 2). Behavior is unchanged: the same values are returned and the same errors are tolerated; what is added is a record.

- The audit: **30 broad handlers** (25 `except Exception`, and 5 `except BaseException` that clean up and re-raise). **None sits
  on a path that can produce a false match or corrupt state**: the code that judges and links a match (`scoring`, `elfobj`,
  `network`, `compiler`, `project`, `rom/match*.py`) has no broad handler at all, and the database wrapper rolls back and
  re-raises. Seven handlers re-raise, ten report through the exception or the GUI, and **thirteen swallowed the error
  without a trace** (7 + 10 + 13 = 30, counted by the same classifier the policy test uses; afterwards: 7 re-raise, 11 report,
  8 log, and the 4 allowlisted stay silent).
- Nine of those thirteen now log through the `decomp.wtf` logger (which the app writes to its log file), with the traceback:
  `agents.py` (three, in `_prepare`: twins and the permuter, the start-files check, starting files), `engine.py` (the twin
  hint, and **the autopilot's per-function handler**, where a crash such as the x86 one fixed in 0.10.22 would have shown only
  as one more function counted "fail"), `forkengine.py` (the background link, the twin hint, the data index), and
  `twins.py` (info level: an unreadable object means a missed free match, never a wrong one).
- The other four stay silent on purpose and are listed, each with its reason, in
  `maintenance/tests/test_maint_exception_policy.py`: a network blip while waiting for a room's host, releasing a claim in a room
  as an agent stops, `literals.py`'s deliberate "no verdict rather than a wrong one", and failing to open a browser on a server.
- Tests, 5 in `test_maint_exception_policy.py` (3 failed before): **a policy test over the whole source tree** that fails when
  anyone adds a broad handler that neither re-raises, reports, nor logs, or leaves a stale allowlist entry; a test that the
  judging and matching code stays free of broad handlers; and two that a failing twin lookup still returns an empty hint
  and now leaves a traceback.
- Verified: **whole suite with every tool: 428 passed and the changelog test this entry satisfies, 52 skipped, 0 failed**; test
  by test against the last full run, nothing dropped, the 32 new tests (added in 0.10.26 to 0.10.29) all pass, nothing regressed.
- Not changed: an unused import (`AUTO_NAME` in `engine.py`) that was already there and that CI's rule set (serious errors only)
  does not cover; fixing unrelated style would mix a refactor into this change.
- Nothing for users to do. If an agent helper or the autopilot misbehaves, the app's log now says why.

## [0.10.28] - 2026-10-21

**Test, Docs.** A guard for the git-installed tools' pins, and a correction to a claim I got wrong. No change to the application.

- **Correction.** The 0.10.18 entry said `m2c` is pinned by a 10-character commit id. That was false: the registry pins `m2c` to
  the full 40-character commit `708d2d2cb2698f091a92492b328f73b24209f72d`, exactly as it pins `luvdis`. I had read the installer's
  progress line, which prints `tc.commit[:10]`. The entry now carries a bracketed correction in place (the text is not rewritten
  silently), and no other document repeated the claim (searched).
- `maintenance/tests/test_maint_toolchain_check.py`: `test_every_tool_installed_from_git_is_pinned_to_one_full_commit`. `m2c` and
  `luvdis` are installed from a git commit rather than a hashed archive, so the commit id is the pin, and a branch name or an
  abbreviated id would not be one (a branch moves; an abbreviation can become ambiguous). Both pass today; the test is a guard
  against a future registry edit, not a fix, so there was no failing state to show.
- Also fixed: a grammar slip in the plan's Phase 2 status row from 0.10.27.
- Nothing for users to do.

## [0.10.27] - 2026-10-21

**Fix.** The luvdis stack fix refuses a luvdis it was not written for, instead of silently doing nothing. (Plan Phase 2:
`luvdis_run.py`.) Touches only `src/decompnet/rom/luvdis_run.py`.

- The problem: the GBA disassembler is run through a script that rewrites a piece of luvdis's source (`source.replace(PUSH,
  SAFE_PUSH, 1)`) to fix a stack emulation bug. If luvdis's code were ever different, the replace changed nothing and the
  script went on with the unpatched program. **Shown by hand against a luvdis that lacks the code: it printed "LUVDIS RAN,
  UNPATCHED" and exited 0**, so the crash it exists to prevent would have returned without any sign that the fix was missing.
- The fix: `patched(source)` insists on finding the code to replace exactly once. Otherwise it exits 1 with "expected the stack
  code it fixes exactly once in luvdis/analyze.py, found it N times. This is not the luvdis commit decomp.wtf pins
  (toolchains.toml), or luvdis has fixed the bug itself: update luvdis_run.py together with that pin." The GBA importer already
  shows the end of a luvdis failure to the user, so the message is seen.
- The plan also said to pin the luvdis version. It already was: a full 40-character commit in `toolchains.toml`
  (`ec3a4e3e...`), and a test now checks it stays one.
- Found while testing: the docstring understates the bug. With the original code a stack pointer of `-1` does not raise, because
  Python's negative indexing **silently overwrites the last word of the stack**; only below `-len(stack)` does it raise
  `IndexError`. So the fix is a correctness fix, not only a crash fix. A test pins both behaviors.
- Verified: 16 tests in `maintenance/tests/test_maint_luvdis_patch.py` (5 failed before): against the **real pinned luvdis**
  (installed with `decomp toolchain install luvdis`) the code to fix occurs exactly once and the patched source compiles;
  the three kinds of mismatch (absent, already fixed, twice) are refused; the script run end to end against a different luvdis
  stops with exit 1 and does not run luvdis; the patched luvdis starts from the script in its own environment; and the
  replacement code does what its docstring says for every stack pointer below zero, and is identical to the original for a normal push.
- Not verified: a full disassembly of a real GBA ROM, which needs `agbcc` and the Arm GNU toolchain to build one (hosts this
  sandbox cannot reach). Run `tests/test_gba.py` on your machine.
- Nothing for users to do.

## [0.10.26] - 2026-10-21

**Security.** What the app writes into other people's projects points at this fork, not at upstream's website. Closes the
last item the 0.10.17 and 0.10.25 entries listed as not done.

- The problem: an exported decompilation is handed to strangers, and its generated `build.py` says, when decomp.wtf is missing,
  **"install decomp.wtf first (https://decomp.wtf)"**, an instruction that sends the reader to the website of a different project,
  which serves upstream's installer. The exported READMEs said "started with decomp.wtf" with the same link and "needs decomp.wtf
  installed" with no source at all. Nine lines in six generator files.
- The fix: `decompnet.HOME_URL` (this fork's repository) and `decompnet.UPSTREAM_URL` (the original, as a credit) in
  `src/decompnet/__init__.py`. The exported READMEs (`rom/export.py`, `rom/export_gba.py`) and the fork-mode scratch READMEs
  (`forks/scratch_dtk.py`, `scratch_dsd.py`) use the constant, and now say *where* to get the tool ("needs decomp.wtf installed
  from <this fork's URL>"). The two build scripts (`rom/export_build.py`, `export_gba_build.py`) are copied into a project and
  run where `decompnet` cannot be imported, which is exactly when their message appears, so the URL is spelled out there; a
  test fails if the literal and the constant ever differ.
- Tests: 10 in `maintenance/tests/test_maint_generated_links.py` (all failed before). They cover the constants; a scan that no
  shipped source file contains `https://decomp.wtf`; both generated READMEs; the fork-mode READMEs; and **the build scripts run for
  real** under a system Python that does not have this package, in a folder laid out like an export (a `build.json` beside the
  script, which the script reads before it checks for the tool: my first version of the test skipped that and failed for the
  wrong reason, which is why it was rewritten).
- Verified: the real messages, from a faithful project folder, now read "install decomp.wtf first
  (https://github.com/FlyPhantomFly/Function_2_C_Decompiler)" (they read the old address before); the upstream tests that run real
  exports, builds and scratch projects pass (36 passed, 21 skipped for compilers and platforms this sandbox lacks).
- Not changed: the *name* "decomp.wtf" in commit messages and generated text ("Edited by X with decomp.wtf"). That is the staged
  rebrand (plan item 1.1): a name, not a link or an instruction.
- Nothing for users to do. Projects exported earlier keep upstream's text in their own `build.py` and README.

## [0.10.25] - 2026-10-21

**Removal.** The retired hosted-network layer is deleted. The owner decided to delete it (plan Phase 2, option (a)). 54 files
changed, 4,245 lines deleted and 200 added (the additions are tests, edits and documentation).

- What went, after an AST import graph (including imports inside functions, and a check for dynamic imports) showed that
  nothing under `app/` reaches it: `src/decompnet/{server,cli,registration,jobs,public,upstream,local}.py` (881 lines: the
  coordinator's HTTP and MCP server, the `decompnet` command, Turnstile signup, donated-compute jobs, public pages, the per-match
  git export, hash-only contributor tools); `site-redirect/`; and the website under `site/` (34 files: pages, the simulation, fonts,
  Cloudflare and Node packaging, build tools, and upstream's legal and privacy pages, which named upstream's operator and contact
  address and described *his* website). The `decompnet` console script is gone from `pyproject.toml`; `decomp` is the only one.
- Also removed: the volunteer half of `permuter.py` (`LocalScorer`, `search`, `_api`, `worker`: HTTP calls to a coordinator, a
  live file whose dead half the import graph cannot see), 239 lines to 130. The mutation helpers the app's local permuter uses stay.
- What stays on purpose: `network.py`, `policy.py`, `project.py` (the core the app builds on), the installers and container files
  in `site/public/`, and the files the import graph cannot see but that are used (scripts the exporter copies into generated
  projects, `luvdis_run.py` run as a subprocess, the DS template's tools). Two leftovers are named, not hidden: **hash-only
  projects** still exist in `network.py` and `project.py` and are tested, but nothing can create one from the app now; and the
  unused `registrations` and `jobs` tables stay in `store.py` so existing databases keep working.
- Fixed on the way: two messages in `network.py` told agents and users to run `decompnet local asm` and `decompnet local diff`,
  commands that no longer exist; they now say plainly that a hash-only project can only answer match or no match.
  `tests/test_phase23.py` keeps its three core tests (reputation gating, hash-only import and match, per-unit headers); its
  helper now creates the untrusted agent with the same `register_agent` call the deleted `Registrar` made. `tests/test_http.py`
  went whole; it tested only the deleted server.
- Dependencies: no declared dependency became unused (checked by import scan; `splat64`, `spimdisasm` and `ninja` are run as
  tools, not imported). The deleted modules' only third-party imports were `anyio`, `starlette` and `mcp`, which the app still uses.
- Tests: 14 in `maintenance/tests/test_maint_legacy_removed.py` (12 failed before), which pin the end state and **fail if an
  orphaned module ever appears again** (every module must be reachable from the app or be a listed script), if a hosted-service
  endpoint returns to the code, if any instruction names a deleted subcommand, or if the permuter grows network code.
  **Whole suite with every tool: 396 passed and the changelog test this entry satisfies, 52 skipped, 0 failed.** Test by test
  against the previous full run, the only items that disappeared are the six legacy tests (two in `test_http.py`, four in
  `test_phase23.py`), the 26 new ones pass (12 from 0.10.24, 14 here), and nothing that passed regressed.
- Documentation: `ARCHITECTURE.md` section 8 describes what was removed and what was kept; section 9 gains an **inventory of the
  hosts the code can contact**, read from the source (not captured traffic), replacing what upstream's privacy page said. Notably the
  app does not contact `decomp.dev` at runtime. The plan, `CLAUDE.md` and the README layout table are updated.
- Not done: generated export files and the export build scripts still link to `decomp.wtf` as text (next version).
- Nothing for users to do: `decomp` is unchanged. Anyone who used `decompnet serve` or its moderation commands should keep upstream's
  tag `upstream-0.10.6`.

## [0.10.24] - 2026-10-21

**Tooling.** `decomp toolchain list | install ID | path ID`, ported from the hosted-network CLI so that CLI can be deleted next.
First step of the legacy-layer removal the owner decided on; no code is deleted in this version.

- Why first: `decompnet toolchain ...` was the only command line way to install or find one specific pinned compiler, and the
  only way to install a proprietary one (`--accept-license`); `decomp setup` installs just the free default set. The old
  command was also named in runtime messages: `toolchains.require` told a user missing a compiler to run it, and so did
  `README.md`, `projects/demo-gc` and `demo-ds` build scripts, `seeds.py`, the registry's comments and several test skip
  messages. Deleting the old CLI first would have left all of them pointing at a command that does not exist.
- `app/cli.py`: new `toolchain` subcommand with `list`, `install ID [--accept-license] [--force]` and `path ID`, with the same
  behavior and output as before (clean `error: ...` on stderr and exit 1 for an unknown id, a missing toolchain or a refused
  license). Every reference above now says `decomp toolchain ...`, including `maintenance/baseline/setup-test-env.sh` and
  `maintenance/CLAUDE.md`. The old `decompnet toolchain` still works until the next version.
- Tests: 12 in `maintenance/tests/test_maint_toolchain_cli.py` (11 failed before): list and installed state, clean errors, the
  flags reaching `install`, **a proprietary compiler is never installed without `--accept-license` and nothing is downloaded
  before that is checked** (all four: `ido-7.1`, `ido-5.3`, `mwcc`, `mwccarm`), and a scan that fails if any file still tells
  anyone to run the old command. Real runs: `list`, idempotent `install`, `path`, the license refusal (exit 1), and the
  rewritten setup script, which now stops only at the zlib download this sandbox cannot reach.
- Nothing for users to do beyond using `decomp toolchain` instead of `decompnet toolchain`.

## [0.10.23] - 2026-10-21

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run E** in `maintenance/baseline/`: the maintained code at 0.10.22, measured the same way as the upstream baseline: **377
  passed, 0 failed, 52 skipped (429 items)** with every free tool and `bwrap`. Test by test, nothing that passed in
  upstream's run C or in run D fails, 64 items are new and pass, and nothing is xfailed. The bare-machine CI commands:
  284 passed, 145 skipped, 0 failed in 16 s.
- `MAINTENANCE_PLAN.md`: Phase 2 is marked started, with what is done (the matching-integrity tests, which found and fixed
  two defects in the core) and what is open (the legacy layer decision, `luvdis_run.py`, the `except Exception` audit,
  schema migrations, refactors). `CLAUDE.md`: invariant 1 notes its guard and the rule to decide a match with `same_as`.
- `maintenance/patches/`: regenerated, 17 patches (0.10.7 to 0.10.23).
- Nothing for users to do.

## [0.10.22] - 2026-10-21

**Fix.** A relocation inside bytes capstone cannot decode no longer crashes scoring on x86 and x86-64. Fixes defect 2 from
0.10.20. Touches `scoring.py` (review-first), as one self-contained version.

- The problem: capstone's SKIPDATA mode turns undecodable bytes into pseudo-instructions (`id == 0`) with no operand
  details. `scoring._symbolize` read `ins.disp_size` on them whenever a relocation fell inside one, which raises
  `CsError`, so `diff(f, f)` itself failed and the function could never be scored. Minimal case: `86 0d` (a truncated
  instruction) with a relocation at offset 1. It failed closed (no false match) and affected only x86 and x86-64; the
  MIPS, PPC, ARM and Thumb paths never read those details (tested). It would bite wherever x86 code embeds data with
  relocations, such as jump tables in `.text`.
- The fix: one condition. The x86 detail-reading branch of `_symbolize` now requires `ins.id`; a placeholder falls
  through to the generic symbolization the other architectures use, so the listing shows `.byte <a+0x1>` for the byte the
  relocation covers. Instructions that decode are untouched (`id` is non-zero), so nothing changes for real code.
- Verified: the xfail test now passes and its marker is removed; a control shows such a function still matches only itself
  (a different symbol or byte scores > 0); the 600-pair random sweep, which tolerated these crashes in 0.10.20, is now
  strict and passes; the other four architectures are tested explicitly. 184 tests pass across the maintenance tests and
  the x86 network suites; ruff is clean on the touched files including unused names.
- Nothing for users to do.

## [0.10.21] - 2026-10-21

**Security (correctness of the core).** A function is only a match for the function it really is. Fixes defect 1 from
0.10.20. This touches `scoring.py`, `elfobj.py` and `network.py`, which are on the review-first list: it is one self-contained
version so that it can be reviewed, or reverted, on its own.

- The problem: `fingerprint()` hashes the masked code and the relocation list as one unframed stream, and three places
  decided "match" by fingerprint equality alone, so a longer function with no relocations, whose tail spelled out the
  relocations' text, was credited as a match: `compile_and_diff` answered `MATCH! ... byte-identical to the target`, the
  hash-only path credited it, and the header re-check called it "still matching" (all three demonstrated in 0.10.20).
- The fix: new `FunctionObj.same_as(other)` compares the masked code and the sorted relocation keys directly, and
  `scoring.diff` uses it. The two hash-only comparisons in `network.py` (crediting a compile, and the header re-check)
  keep the fingerprint and also require the candidate's length to equal the `size` stored with it; the header re-check
  uses `same_as` where the target is stored. **A legitimate match can never be rejected by this:** equal masked code and
  equal relocations have equal length by definition, and the stored size is `len(code)` of the target (`project.py`). The
  fingerprint algorithm and every stored fingerprint are unchanged, so no migration and no invalidated data.
- Verified: the four tests that failed in 0.10.20 pass (their `xfail` markers are removed in this change, as strict xfail
  requires), with the three controls beside them. **Whole suite with every tool: 372 passed, 55 skipped, 1 xfailed (defect
  2), 0 failed. Test by test against the previous full run: nothing that passed fails, 63 items added, none dropped.**
- Still true, and pinned by `test_known_limitation_the_fingerprint_alone_cannot_tell_these_two_functions_apart`: the
  fingerprint by itself remains ambiguous, so any new code that has both functions must use `same_as`, and code that has
  only a stored fingerprint must also check the size. A reframed fingerprint would fix it at the root but invalidates
  stored fingerprints (hash-only projects, DBs), so it needs a versioned migration and is left as a decision for you.
- Nothing for users to do.

## [0.10.20] - 2026-10-21

**Test.** Matching-integrity tests for `scoring.py` and the three places a match is decided. They found two defects, which
are pinned as strict `xfail` tests and fixed in the next two versions. No change to the application. (Plan Phase 2.)

- `maintenance/tests/test_maint_scoring.py` (57 tests): a score of 0 happens **exactly** when the functions are the same,
  checked on 600 seeded random pairs against an oracle that does not use the hash; every kind of near miss costs exactly its
  documented penalty (1, 5, 10, 60, 100, 100) and keeps its order; the same instruction text in two encodings scores 1;
  relocation normalization is exact (**all 17 entries of the mask table, 2,176 single-bit flips: bits in a masked field are
  ignored, every other bit changes the fingerprint**); relocations cannot be traded for different ones (symbol, type, addend,
  position, missing, extra) or hide a neighbouring register or opcode bit (MIPS `lui`/`jal`, PPC `bl`); percentages never read
  100% before a match. On **real gcc output** (the demo's 13 functions): they match themselves, `-O0` never matches `-O2`, and
  **none of 1,212 bit flips in bytes outside relocations produced a match**, while changing the bytes a relocation fills in
  still matches. Needs `gcc`; the rest runs anywhere.
- `maintenance/tests/test_maint_match_integrity.py` (6 tests): for `scoring.diff`, the hash-only comparison and the header
  re-check in `network.py`, a control (a real solution is still credited) beside a forgery.
- **Defect 1, found (strict xfail, fixed in 0.10.21).** `FunctionObj.fingerprint()` hashes the masked code and the
  relocation list as one stream with no length or separator, so a longer function with no relocations whose bytes are the
  target's masked code followed by the text of its relocations has the same fingerprint. Demonstrated through the real
  code: `compile_and_diff` replied `MATCH! rng_next is byte-identical to the target`, the hash-only path credited it, and the
  header re-check reported nothing broken. Severity: low in practice, because C source compiled by the real toolchain cannot
  produce such bytes (the tests substitute the compiler's output); it is still a hole in the one invariant that matters.
- **Defect 2, found (strict xfail, fixed in 0.10.22).** On x86/x86-64, a relocation that falls inside bytes capstone cannot
  decode (e.g. a 2-byte truncated instruction `86 0d` with a relocation at offset 1) makes `scoring.disassemble` raise
  `CsError`, so `diff(f, f)` itself fails and the function can never be scored. It fails closed (no false match). MIPS, PPC,
  ARM and Thumb are not affected (tested). It matters where x86 code embeds data with relocations (jump tables in `.text`).
- Checked and fine: `percent_text` right up to the edge of 100; the mask table; the penalties.
- Not covered: the ROM-link verdict in `app/engine.py` (it compares real bytes in the linked ROM, so it does not use the
  fingerprint), the `twins` fingerprint (grouping only), and `forks/` judging (objdiff).
- Nothing for users to do.

## [0.10.19] - 2026-10-21

**Docs.** Status, the final measurements, and the patch set. No change to the application.

- `maintenance/MAINTENANCE_PLAN.md`: a status table (what is done, in which version, what is left) and "your next steps";
  the fork-name decision is recorded as made. It says plainly what is **not** done: the product-name rebrand, Phase 2
  (the scoring property tests are the recommended next piece of work) and the legacy layer, and CI having never run on
  GitHub. `maintenance/CLAUDE.md` gains the installer/plugin invariant and the checker command;
  `maintenance/README.md` lists the new tool.
- `maintenance/baseline/`: **run D**, the maintained code measured the same way as upstream's runs A to C.
  With every free tool and `bwrap`: **310 passed, 55 skipped, 0 failed (365 items)**. Test by test against run C:
  nothing that passed there fails now, the one test that failed there passes, 95 of the 97 new tests pass and 2 skip
  (no PowerShell), and the one upstream test I renamed is accounted for. On a bare machine (the commands of CI's `checks`
  job): 220 passed, 145 skipped, 0 failed. What still skips is what needs compilers or platforms this sandbox lacks.
- `maintenance/patches/`: one `git am` patch per version, 0.10.7 to 0.10.19, and `tools/make_patches.sh` to regenerate
  them. Verified against your real repository: a clone of `FlyPhantomFly/Function_2_C_Decompiler` at `575b4a3` has the
  same tree hash as my import of upstream 0.10.6 (`f65de84`, 273 files), and `git am` of the patches onto it applies
  cleanly and produces a tree identical to this one (minus the patches folder). The commits are authored "Maintainer
  (Claude session)"; `maintenance/patches/README.md` shows how to re-author them as yourself.
- Nothing for users to do.

## [0.10.18] - 2026-10-21

**Tooling, CI.** A checker for the pinned compiler downloads. (Plan item 1.7.)

- `maintenance/tools/check_toolchains.py`: reads `src/decompnet/toolchains.toml` and (1) enforces the registry's rules
  (every download is https and has a 64-hex `sha256`), (2) checks every unique URL still exists (HEAD, falling back to a
  one-byte GET for hosts that refuse HEAD), (3) with `--verify`, downloads each file and compares its sha256 with the
  pin. Failures are classified: `dns` (this machine can't resolve the host, often only its network), `http` (a dead
  link), `sha` (the file changed under its pin), `timeout`, `tls`. Exit 1 on any failure.
- Why: every compiler this app runs comes from a third-party URL. Links rot, and `toolchains.install` accepts an entry
  with no hash and "pins it on first use", which would install unverified code. `install()` is not changed (it is on the
  review-first list and all 62 parts are pinned today); instead
  `maintenance/tests/test_maint_toolchain_check.py::test_every_download_in_the_real_registry_is_https_and_pinned_by_sha256`
  fails if anyone adds an unpinned or non-https entry.
- CI: a `toolchain-urls` job (nightly and on demand) runs it, `continue-on-error` until its first run on a runner shows
  whether hosts such as developer.arm.com answer a build server; delete that line then.
- Verified against the real registry, from the sandbox: 58 unique downloads in 23 toolchains, **52 resolve (all GitHub),
  0 rule violations, 0 dead links**; the 6 failures are all `dns`, on `archive.archlinux.org`, `snapshot.debian.org`,
  `developer.arm.com` and `files.decomp.dev`, which this sandbox cannot reach (run it on your machine to cover them).
  `--verify` on `gcc-2.7.2-kmc`, `gcc-2.7.2-psx`, `binutils-mips` and `objdiff-cli`: 14 real files downloaded, **all 14
  sha256 match their pins**. 7 tests, offline (a local HTTP server stands in for the hosts: live, 404, HEAD refused,
  file changed, unresolvable host, and the exit codes).
- Not covered: tools installed from a git revision instead of a hashed archive (`m2c`: pinned by a 10-character commit
  id), and the hosts above until run elsewhere. **[Correction, 0.10.28: wrong. `m2c` is pinned by a full 40-character commit,
  like `luvdis`; ten characters appear only in the installer's log line. The checker still does not cover git-installed
  tools, but a test now pins that their commits are full.]**
- Nothing for users to do.

## [0.10.17] - 2026-10-21

**Security.** The app's own links, the team-room page and the Claude Code plugin send people, and agents, to this fork
only. (Plan item 1.1, the live-app half.)

- **The plugin's skill told the AI agent to run `curl -fsSL https://decomp.wtf/install.sh | bash`** (and an `irm ... | iex`
  for PowerShell) when the decomp tools were missing. An agent follows such a line. `SKILL.md` now says: ask the user,
  then clone this repository and run `bash site/public/install.sh` from it (needs bubblewrap; on Windows, from a Linux
  shell in WSL 2), and never run an installer the user did not give it or fetch one from another address.
- `plugin.json` and `marketplace.json`: author/owner `PhantomThreads`, homepage and repository this fork. The plugin's
  own version moves 0.9.8 to 0.9.9 (both files) because its skill text changed and clients use that number to see
  updates. The names `decomp-wtf` stay, so `/plugin install decomp-wtf@decomp-wtf` still works with the marketplace
  added from this repository (README updated in 0.10.15).
- `static/app.js` and `static/index.html`: the bug-report and issue links go to this fork's issues; Settings shows
  "Source code" (this fork) and "Original project" (upstream's repository, a credit and the only upstream link left in
  the app). The row that linked to upstream's website is gone. `app/collab.py`: the team-room page's "Don't have the
  app?" link goes to this fork.
- Tests: 5 in `maintenance/tests/test_maint_links.py` (all failed before): no page links to `https://decomp.wtf`; exactly
  one upstream link, the credit; bug-report, source and join links go to this fork; the skill never pipes a download
  into a shell or names upstream; manifests agree on name, owner and version. `app.js` still parses (`node --check`);
  150 related tests pass (28 skipped for missing compilers).
- **Not changed, still open:** the legacy hosted-network layer. The old `decompnet` admin CLI (`src/decompnet/cli.py`)
  still prints an invitation line `curl .../network.sh | bash` built on `https://decomp.wtf`, and `server.py` builds
  that command. That is the retired hosted service, which the plan decides to delete or keep (Phase 2); do not send
  those printed lines to anyone meanwhile. Also not changed: the marketing site under `site/` and the many `decomp.wtf`
  product names in app text (the staged rebrand).
- Nothing for users to do; plugin users re-add the marketplace from this repository.

## [0.10.16] - 2026-10-21

**Security.** The updater never offers a downgrade. (Found while installing from a clone for real, after 0.10.15.)

- The problem: an install made from a clone records `channel = branch` and the clone's commit. If that commit was never
  pushed, GitHub answers 404 to the compare call, and `_check_branch` ignored that and offered the branch's newest
  commit as an update, whatever it contained. Demonstrated with real data: your repository's `main` is `575b4a3`, which
  is still upstream's untouched 0.10.6 (with the old, upstream-pointing updater). The previous updater, installed from
  an unpushed 0.10.15 tree, offered "update to 0.10.6" and a one-click install of that archive.
- The fix, in `src/decompnet/app/updates.py`: a branch commit is only an update if its `pyproject.toml` version can be
  read and is not older than the installed one. Commits at the same version still count (normal work between bumps),
  newer versions still count. Same demonstration on the fixed code: not offered.
- Tests: 5 added to `maintenance/tests/test_maint_updater.py` (3 failed before: unpushed install with older branch,
  older version with a known commit, unreadable version). `tests/test_updates.py::test_branch_update` stubbed the branch
  version as `0.10.0`, which is older than any version of this fork and so encoded the old behavior; its stub is now
  `99.0.0` and it still covers the update flow. 31 updater tests pass.
- Cost of the safe choice: a branch whose version line can't be fetched is never offered, until the fetch works.
- **Push this work to `main` before relying on it:** the app compares against your repository, and until its `main`
  holds this code, any installed copy is rightly told it is ahead.

## [0.10.15] - 2026-10-21

**Security.** The installers install this fork's code or nothing; the README no longer tells anyone to run upstream's.
(Plan item 1.1, the installers and the install instructions.)

- Before: the README's install commands (`curl ... decomp.wtf/install.sh | bash`, and the same from upstream's GitHub)
  ran upstream's installer, which, piped from curl, fetched upstream's wheel from the decomp.wtf website (falling back
  to upstream's GitHub tag); `--source branch:<name>` installed *upstream's* branch; `dev.sh` and `dev.ps1` piped
  upstream's installer into a shell; `install.ps1` downloaded scripts from decomp.wtf and ran them as root inside WSL;
  `docker-compose.yml` installed the `release` (upstream's) on first start. Even run from a checkout, `install.sh`
  recorded `--repo i12bp8/decomp.wtf`.
- `site/public/install.sh`: `REPO` is this fork's. The `release` source now refuses (this fork publishes no release and
  has no download site) with instructions, unless the user names a package with `DECOMP_WHEEL`. Run from a checkout it
  installs that checkout, as before, and fetches no code. `dev.sh` runs this fork's installer from this fork's
  GitHub. Messages no longer tell Linux users to run a PowerShell command from decomp.wtf.
- `install.ps1`, `dev.ps1`: refuse at the top, before any network call, saying why. Windows is not supported by this
  fork yet (plan: frozen). `docker-compose.yml`: `DECOMP_SOURCE: branch:main`, which installs this fork's main branch
  from GitHub on first start.
- `README.md`: a fork notice above upstream's own notice (kept as its author wrote it, including the request to use
  this only on games you own); the Install section is clone-and-run with the bubblewrap requirement; issue links, the
  Claude Code plugin line and the server and branch-testing instructions point at this fork. The two links left to
  upstream are credits to its repository.
- Verified: 14 tests in `maintenance/tests/test_maint_installers.py`, which run the real `install.sh` and `dev.sh` with
  recording stand-ins for `curl`, `uv` and `decomp` and assert on every call (12 failed before the change). The two
  PowerShell scripts were parsed with a real PowerShell 7.6.6 (downloaded and its sha256 checked against Microsoft's
  published file) and executed: both exit 1 at the guard; the parser was shown to reject a broken file. **The documented
  command was run for real** from a clone, with an isolated `HOME`: exit 0, installed `decompnet 0.10.14`, compilers
  downloaded from their pinned GitHub release URLs, `install.json` records this fork's repo, no proprietary license
  accepted.
- Not verified: the Docker route (no Docker here; checked by reading). Not changed: the marketing site under `site/`,
  the legacy hosted-network layer, and the many `decomp.wtf` names in app text (the staged rebrand, plan item 1.1).
- Users: install with the commands in the README. `curl ... | bash` no longer installs anything.

## [0.10.14] - 2026-10-21

**Docs.** Attribution and package metadata. (Plan item 1.3.)

- `LICENSE`: added `Copyright (c) 2026 PhantomThreads` under upstream's `Copyright (c) 2026 Sam Wolfs`. The original
  notice and the MIT permission text are unchanged and stay first, which is what the license requires of a fork.
- `pyproject.toml`: `maintainers = [PhantomThreads]` (the original author stays under `authors`); `Homepage` and
  `Source` now point at `github.com/FlyPhantomFly/Function_2_C_Decompiler`; a new `Upstream` link credits
  `github.com/i12bp8/decomp.wtf` (a credit, nothing downloads from it). The `decomp.wtf` website is not this fork's.
- Verified: 3 tests in `maintenance/tests/test_maint_attribution.py` (failed before); `uv lock --check` passes; a real
  wheel was built and its `METADATA` shows `Author: sam wolfs`, `Maintainer: PhantomThreads`, the three links and
  `License-File: LICENSE`.
- Not changed: the name "decomp.wtf" in code and text. It is upstream's brand, not covered by the MIT license, and
  replacing it is the staged rebrand (plan item 1.1), still open and separate from this change.
- Nothing for users to do.

## [0.10.13] - 2026-10-21

**CI.** GitHub Actions workflow `.github/workflows/ci.yml`. (Plan item 1.6.)

- `checks` (every push to `main` and every pull request, bare machine): `uv sync --locked`, `uv lock --check`,
  version agreement across the three places, `compileall` (including `site/` and `projects/`), `ruff` limited to
  syntax errors, undefined names and bad comparisons (`E9,F63,F7,F82`), then the whole test suite. Skips are listed with
  their reasons in the job summary and `junit.xml` is uploaded.
- `sandbox` (every push and pull request): installs bubblewrap, checks it can really create a sandbox, and runs the
  sandbox tests plus the tests that compile agent code inside it. **`continue-on-error: true` for now** (see below).
- `toolchains` (nightly, and on demand): runs `maintenance/baseline/setup-test-env.sh` (free toolchains, zlib source)
  and the whole suite with compilers.
- Supply chain: the three actions are pinned to full commit SHAs, each resolved from the repository, not typed from
  memory, and one release back for `setup-uv` (v10.2.0) and `upload-artifact` (v7.0.1) because the newest were under two
  weeks old. The token is read-only, there are no secrets, no `pull_request_target`, and checkout does not persist
  credentials. `maintenance/tests/test_maint_ci_workflow.py` (6 tests) fails if any of that is loosened.
- Why not the default `ruff` rules: they report 428 style findings in the inherited code, and reformatting it would
  mix a large refactor into this change. Revisit once the code is ours.
- Verified here: `actionlint` passes the workflow (exit 0) and rejects a deliberately broken one (exit 1), so the check is
  real; every command of `checks` ran in order on a machine with no `bwrap`, `lld`, `llvm-objcopy`, toolchains or
  zlib source, ending **188 passed, 143 skipped, 0 failed in 12 s**; the `sandbox` job's commands ran with `bwrap`
  (40 passed).
- **Not verified, because it cannot run outside GitHub:** the workflow itself on a runner. Specifically (1) whether the
  Ubuntu 24.04 runner allows bubblewrap to create namespaces after the `kernel.apparmor_restrict_unprivileged_userns=0`
  step, which is why `sandbox` may fail without failing the build until its first run shows otherwise; (2) the nightly
  job end to end (its script was run here; the runner was not). Look at the first runs and adjust.
- Nothing for users to do. To use it, push this tree to the repository and enable Actions.

## [0.10.12] - 2026-10-21

**Dependencies.** `mcp` is bounded to the 2.x API the app is built on. (Plan item 1.5, the bound.)

- `pyproject.toml`: `mcp>=2.3.0` became `mcp>=2.3.0,<3`. The app imports `mcp.server.mcpserver` and `mcp.Client`, which
  exist only in 2.x; with no ceiling, anything that installs without `uv.lock` could pick up a future 3.x.
- `uv.lock` regenerated with `uv lock`: the diff is the one specifier line, and `mcp` stays at 2.3.0. `uv lock --check`
  and `uv run --locked` pass.
- Tests: `maintenance/tests/test_maint_dependencies.py` (the bound excludes 3.0.0 and includes 2.3.0 to 2.99; the
  installed `mcp` satisfies it and has the modules the app imports). The bound test failed before the change.
- Nothing for users to do. Installing from the lock file is unchanged; `uv sync --locked` is still the way (CI will use it).

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
