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
  id), and the hosts above until run elsewhere.
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
