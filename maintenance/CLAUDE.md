# Working on this repository

This is a maintained fork of `decomp.wtf` (Python package `decompnet`, upstream 0.10.6, MIT, by sam wolfs). It
orchestrates LLM agents that write C which a period compiler builds and a judge compares byte for byte. Read
`maintenance/ARCHITECTURE.md` for how it works and `maintenance/MAINTENANCE_PLAN.md` for what to do next.
`maintenance/CHANGELOG.md` is the record of what has been done.

## Commands (all of these have been run on this code)

```sh
uv sync --locked                                  # install exactly what uv.lock says
uv run --locked pytest -q -rsfE                   # the suite (tests/ and maintenance/tests/)
uv run --locked decomp toolchain list             # which pinned compilers/tools are installed
uv run --locked decomp toolchain install ID       # install one (sha256-verified); ID from the list
maintenance/baseline/setup-test-env.sh            # apt packages + free toolchains + zlib source, safe to re-run
python3 maintenance/tools/summarize_junit.py junit.xml   # needs: pytest --junitxml=junit.xml
python3 maintenance/tools/bump_version.py --check        # do the three version places agree?
python3 maintenance/tools/check_toolchains.py            # does every pinned compiler download still exist? (--verify: hash them)
```

Entry point (from `pyproject.toml`): `decomp` is the local app (`decompnet.app.cli`); it is the only one since the hosted
network's `decompnet` command was removed in 0.10.25. Python 3.12 or newer.

A skipped test names what it needs in its reason (`-rs`). Many skips are expected: PS2, GBA, DS, GameCube and
Windows tests need compilers or platforms that may not be installed. Compare a run with
`maintenance/baseline/summary-C.md` (218 passed, 1 failed (a timing flake), 50 skipped on the reference machine).

## The release rule (every change, no exceptions)

1. One change per version. Do not mix a refactor with a behavior change.
2. Bump with `python3 maintenance/tools/bump_version.py X.Y.Z`. It moves `pyproject.toml`,
   `src/decompnet/__init__.py` and `uv.lock` together. Use the next patch number.
3. Add a `## [X.Y.Z] - YYYY-MM-DD` entry at the top of `maintenance/CHANGELOG.md`: what changed, why, how it was
   verified, and anything the user must do. `maintenance/tests/test_maint_release_hygiene.py` fails otherwise.
4. Put new tests in `maintenance/tests/` (name files `test_maint_*.py`; `tests/` keeps upstream's). Every fix gets a
   test that fails before the fix and passes after.
5. Everything we generate (docs, scripts, tests, baselines, patches) lives in `maintenance/`. Edits to upstream's own
   files are unavoidable but stay minimal. The only things outside the folder are the one-line root `CLAUDE.md` and
   `.github/workflows/` (GitHub requires that path).
6. Do not move `VERSION` in `site/public/install.sh` or `install.ps1`: it names a wheel that must exist on a server.
   The plugin manifests under `.claude-plugin/` and `plugins/` are a separate version track.

## Invariants (a change that breaks one is wrong, whatever else it does)

1. Score 0 is the only way a function becomes matched. (Guarded since 0.10.20 by `maintenance/tests/test_maint_scoring.py` and
   `test_maint_match_integrity.py`. Decide a match with `FunctionObj.same_as`, never by fingerprint equality alone.)
2. Agents cannot run their own compiler for anything that counts.
3. A shared-header edit that breaks any earlier match is rejected.
4. A fork-mode edit that breaks an earlier match is rolled back; agents never write build files or assembly.
5. Nothing is ever pushed upstream, or to any remote, automatically.
6. No ROM bytes or assembly cross a team-room connection.
7. The app contacts no update host except this fork's repository (`updates.REPO`), installs nothing from anywhere else,
   and with `REPO` empty contacts nothing. (True since 0.10.10.)
8. Agent-written C only ever compiles inside the sandbox, unless `DECOMP_UNSAFE_NO_SANDBOX=1` is set or this is
   upstream's own marked Linux or a container. `trusted=True` never changes that: it only skips the source filter.
   (True since 0.10.11.)
9. The installers, the README's instructions, the app's links, the plugin's agent skill and the files the app writes into
   other projects (exported READMEs and build scripts) send people and agents to this
   fork's repository and nowhere else, and nothing tells an agent to pipe a download into a shell. (True since 0.10.15
   and 0.10.17; `maintenance/tests/test_maint_installers.py` and `test_maint_links.py` guard it. The hosted-network
   layer that used to print upstream's invitation line was deleted in 0.10.25.)

## Needs the owner's review before it merges

Anything touching `src/decompnet/compiler.py`, `scoring.py`, `forks/policy.py`, `app/collab.py` or `toolchains.toml`.
Also: any change to the pinned sha256 values, anything that adds a network call, and anything that changes what the
updater or the installers fetch.

## Do not

- Accept a proprietary compiler license (IDO, mwcc, mwccarm) on the user's behalf.
- Run agents against a real commercial game's data in CI. Use `projects/demo-*` only.
- Add a download to `toolchains.toml` without an https URL and a sha256 (a test fails), or install one unpinned.
- Add a broad `except Exception` that neither re-raises, reports nor logs: `maintenance/tests/test_maint_exception_policy.py` fails,
  and the judging code (`scoring`, `network`, `compiler`, `project`, `rom/match*`) must have none at all.
- Change the database format (`store.py`) without raising `SCHEMA_VERSION` and adding a test that opens a database from the version
  before (`test_maint_schema.py`; the 0.10.6 fixture was made by upstream's own code).
- Add a module nothing reaches: `test_maint_legacy_removed.py` fails unless it is imported from `app/` or listed as a script.
- Bypass a sha256 pin to make a download work. A pin that fails means the file is not the one that was reviewed.
- Rename `.decomp.wtf.json` or other on-disk names as part of a branding change; they are file formats, and renaming
  them breaks existing projects. Classify each `decomp.wtf` reference (network endpoint, file-format name, comment,
  marketing copy) before replacing it; plan item 1.1 is a staged rebrand, not a global find-and-replace.
