# Function_2_C_Decompiler (decomp.wtf / `decompnet`): technical write-up

Based on a read of `Function_2_C_Decompiler-main.zip` (273 files). Sections 1 to 9 come from reading the code; each claim in section 10 is marked as read or as verified by running it. Since 0.10.7 the test suite has been run (see `baseline/`), and section 10 says what that confirmed and what is still open.

## 1. What it is

An orchestrator that lets **LLM agents do matching decompilation** of games the user owns. It does not decompile anything itself. It:

1. splits a ROM, disc or executable into functions and data,
2. hands an agent one function at a time with the target assembly, context and a machine-made first draft,
3. compiles the agent's C with the **game's original period compiler** (KMC GCC, IDO, CodeWarrior, agbcc, EE-GCC and others),
4. compares the result with the original **byte for byte** (after relocation normalization),
5. stores matches, notes and shared headers, and shows progress in a local web UI.

"Matching" means score 0, byte-identical code. A function that does not reach 0 does not count.

Two entry modes:

| Mode | Engine | Judge | Source of truth |
| --- | --- | --- | --- |
| **ROM** (from scratch) | `app/engine.py` (`RomNetwork`) | own compile + link at the original address + `scoring.py` (MIPS, ARM), or objdiff inside a generated project (GameCube/Wii/DS) | the user's ROM/disc |
| **Fork** (continue a public decomp from decomp.dev) | `app/forkengine.py` | the project's own build (ninja/make) + **objdiff** | the project's git tree, branch `decomp-wtf` |

Provenance: upstream is `i12bp8/decomp.wtf` by Sam Wolfs, version **0.10.6**, **MIT**. The upstream README opens with a notice that the project is discontinued. The author stopped after objections from parts of the decomp community to AI decompilation. The code is left as-is under MIT.

## 2. Size and shape

- ~20.9k lines of Python in `src/decompnet`, ~5.4k lines in `tests/` (263 collected test items in 37 files) and `maintenance/tests/` (our additions, 186 items), plus a vanilla-JS front end (`app/static/app.js`), the installers and container files (`site/public/`) and a Claude Code plugin (`plugins/decomp-wtf`).
- Largest modules: `app/forkengine.py` 2396, `app/engine.py` 1730, `app/server.py` 1245, `app/agents.py` 1110, `app/collab.py` 844, `network.py` 781, `forks/scratch_dtk.py` 740, `app/twins.py` 694.
- Python 3.12+, built with `uv` / `uv_build`. Dependencies: capstone, mcp (2.x), pyelftools, splat64, spimdisasm, rabbitizer, httpx, uvicorn, ninja (plus truststore on Windows and zstandard on Linux). There are two console scripts: `decomp` (the app) and `decompnet` (the older network CLI).

## 3. Module map

```
src/decompnet/
  network.py        Coordinator core: agents, claims (30 min TTL), attempts, notes, shared header,
                    claim strategies (easiest / finish / closest / hardest / random)
  compiler.py       Sandboxed compile of agent C (bwrap | docker | none | WSL), source filter, rlimits
  scoring.py        capstone disassembly, relocation-aware normalisation, asm-differ-style score
  elfobj.py         ELF object parsing, function extraction, fingerprints
  store.py          SQLite schema + migrations (agents, projects, functions, claims, attempts, notes, events, symbols, ...)
  policy.py         reputation levels and compile budgets
  toolchains.py/.toml  Pinned compiler registry: URL + sha256, per-platform parts, proprietary entries gated by --accept-license
  hostenv.py, wsl.py, limits.py   Where it runs (native / WSL2 / Docker), path translation, memory caps via systemd scopes
  similarity.py, seeds.py, handwritten.py, permuter.py   look-alike search, seeds, hand-written asm detection, decomp-permuter-style mutation
  rom/              ROM/disc readers (n64, psx, ps2, gba, chd), splat driver (split.py), symbol table,
                    matcher (match.py, match_arm.py), overlays/n64code, export of a rebuildable project (export*.py)
  forks/            Fork mode: decomp.dev catalog, project detection/setup, objdiff wrapper, C-source editing,
                    guard rails (policy.py), dtk/ds-decomp scratch project generators, file splits, data diffs,
                    Ghidra + m2c drafts
  app/              The local app: engine, forkengine, tools (MCP tools + prompts), agents (running agents),
                    server (GUI API + MCP), collab (team rooms), twins, permute, updates, connect, service,
                    backup (`decomp backup` / `restore`: a verified, WAL-safe snapshot of the project database, section 7),
                    static/ (GUI), guide/ (agent knowledge base, ~20 markdown guides)
```

## 4. The core loop

1. **Import.** `RomNetwork.import_rom` detects platform and compiler (`rom/detect.py`). It splits with splat/spimdisasm, or decomp-toolkit for GameCube/Wii, ds-decomp for DS and luvdis for GBA. Functions go into SQLite with instruction counts, units and "twin" boosts.
2. **Claim.** An agent calls `claim_function(count=N)`. `network.py` picks by strategy. A claim lasts 30 minutes. Released functions go to the back of the queue for 15 minutes. "Twins" (code that occurs more than once) are served first because one match yields many. Small functions are batched.
3. **Brief.** The agent gets compact assembly, referenced data, callers, best previous attempt, notes, an m2c/Ghidra draft and identical matched code.
4. **Attempt.** `compile_and_diff` sends C source. `compiler.check_source` rejects asm, pragmas, system includes and path traversal. `compile_source` writes `context.h` + `func.c` into a temp dir and runs the pinned compiler in the sandbox. `elfobj` extracts the function. `scoring` normalizes relocations and scores. A score of 0 marks the function matched and saves it. Anything else returns a diff (`<`/`>` missing/extra, `i` operands, `o` order, `r` registers, `s` stack) with a "move on" hint after about 4 stalled compiles.
5. **Share.** `edit_context` changes the shared header. The change is accepted only if every existing match still matches. `rename_symbol` is safe because matching is by address. `add_note` records quirks.
6. **Free matches.** `app/twins.py` matches identical code from its matched twin with names swapped. `app/permute.py` runs a background permuter on near-misses (95%+). An autopilot compiles machine drafts.
7. **Export.** `export_rom` writes a normal decomp tree (matched C, rest as asm, linker script, `build.py`) and proves it rebuilds the game byte for byte.

## 5. Fork mode specifics

- `forks/catalog.py` fetches the decomp.dev project list. `forks/project.py` detects layout (dtk-template, `configure.py` + ninja, splat + make) and runs setup.
- Agents may write only C/C++ sources and headers. They may never touch build scripts, targets or assembly, and inline asm is refused (`forks/policy.py`). Any change that breaks a previously matched function is rolled back.
- Every match becomes a git commit on the local `decomp-wtf` branch. **Nothing is ever pushed or sent upstream automatically.** Keep this invariant.
- For dtk-template projects (`forks/dtksplits.py`, `scratch_dtk.py`) the app can create source files for uncovered code, split files, and flip finished files to "Matching" once the whole-game checksum passes ("linked").

## 6. Agents and MCP

- `app/tools.py` defines the MCP tool set (`claim_function`, `compile_and_diff`, `release_function`, `get_context`, `edit_context`, `find_similar`, `rename_symbol`, `split_function`, `guide`, `start_agents` ...) and the work prompts (`WORK_PROMPT`, `FORK_PROMPT`).
- `app/agents.py` launches agents. CLI agents (Claude Code, Codex, Antigravity CLI, opencode) run headless against the local MCP endpoint. A built-in loop talks to any OpenAI-compatible API (DeepSeek, OpenRouter, llama.cpp, Ollama, LM Studio) and trims context to fit.
- `app/connect.py` and `plugins/decomp-wtf` let a user's own terminal agent drive the app (`decomp connect`, `decomp mcp`).
- Agents get only the decomp tools: no shell and no file access beyond a fork's source tree.

## 7. Persistence, multi-user, platforms

- **State:** SQLite via `store.py` (WAL; additive migrations inline, the format version in `PRAGMA user_version`, a backup kept before the first migration, a newer database refused) in `~/Decomp` (`$DECOMP_HOME`). Logs in `.decomp/logs/decomp.log`.
- **Spend:** project totals in the project config (what the budget cap reads) and, since 0.10.47, `spend_log` (provider, agent, model, dollars, tokens per charge), written in one transaction. One global cap; prices per endpoint (`price_in`, `price_out`, `price_cached`, USD per million tokens) let a priced API model's spend count, and a provider-reported cost wins. Untagged spend is shown as such.
- **Runs:** `decomp run` (`app/runs.py`, schema 3 `runs` table): a controller in the app, not in the CLI. The queue is the functions open at the start and is fixed for the run; completed = matched; the checkpoint is the database itself, the `runs` row only records what is being resumed. Ends as `complete`, `budget`, `stopped`, `ended` (agents gave up, with the reason), or `interrupted` (the app stopped or died; recovered at start-up). Resume continues the latest unfinished run; with none it starts fresh. Never charges anything itself.
- **Backups:** `decomp backup [DEST]` and `decomp restore FILE --yes` (`app/backup.py`). A snapshot uses SQLite's online backup API, because a plain copy of `decomp.db` can miss committed work still in the `-wal` file; it is verified before it is renamed into place. Restore refuses while the app runs, works on a copy of the backup, keeps the database it replaces (`decomp.db.before-restore-<time>`) and removes stale `-wal`/`-shm`. The database only: API keys and settings are in `settings.json` and are not in a backup. Automatic ones (`app/autobackup.py`, since 0.10.49): a daily verified snapshot into `<home>/backups/auto/` with a `.sha256` beside it, kept 3 daily, 2 weekly, 1 monthly, and a weekly restore test whose result the app shows; off with the setting or `DECOMP_NO_AUTO_BACKUP=1`. They share the database's disk. the first migration of an old database keeps its own copy (`.bak-v<old version>`, section 10, item 15).
- **Team rooms:** `app/collab.py` and `forkroom.py`. One host hands out functions, verifies every match against its own copy, and shares only names, structs and notes. No ROM bytes or assembly cross the wire. Exposure is via a Cloudflare quick tunnel (`cloudflared` is a pinned toolchain) or your own address.
- **Platforms:** GameCube/Wii and N64 are "recommended". PS1, PS2, GBA and DS are beta. Windows runs inside its own WSL2 distro. macOS is unsupported.
- **Toolchains:** 25 registry entries (`toolchains.toml`) with sha256 pins on every download part. Proprietary ones (IDO 5.3/7.1, mwcc, mwccarm) are installed only after explicit license acceptance. Old 32-bit compilers run on a pinned i386 glibc runtime inside the sandbox.

## 8. The retired hosted-network layer (removed in 0.10.25)

Upstream once ran decomp.wtf as a public coordinator at `api.decomp.online` next to the local app, and its code was still in
the repository: `server.py` (the coordinator's HTTP and MCP server), `registration.py` (Cloudflare Turnstile signup),
`jobs.py` and the volunteer half of `permuter.py` (donated compute), `public.py` (website JSON), `upstream.py` (per-match git
commits with credit), `local.py` (hash-only contributor tools) and `cli.py` (the `decompnet` command), plus the website under
`site/`, the redirect worker in `site-redirect/`, and the website's legal and privacy pages. The import graph showed `app/` needs
none of it (it builds on `network.py`), so it was deleted; `decomp toolchain` (the one useful part of that CLI) was ported first.
What was kept on purpose, because the app's core uses it: `network.py`, `policy.py` (reputation levels), `project.py`, and the
installers in `site/public/`. What is left over and **no longer functional as a feature**: **hash-only projects** (`verification = "hash"`, kept in
`network.py` and `project.py`, tested, but nothing can create one from the app), and the unused `registrations` and `jobs` tables
in `store.py` (left in the schema so existing databases keep working). **Decision (owner, 0.10.33): leave the hash-only mode in
place and record that it no longer works as a feature.** Its code and tests remain (the matching-integrity fixes of 0.10.21 cover it);
it was the contributor side of the hosted network, whose client tools are gone, and nothing in the app creates or serves such a project.

## 9. Security model (as implemented)

- The app listens on **127.0.0.1 only**. The GUI needs a per-launch secret (URL, then same-site cookie). Agents need bearer tokens, and MCP restricts allowed hosts and origins. Team rooms deliberately bind wider (`0.0.0.0` on a chosen port) when you host.
- Compiles run with `prlimit` (2 GB address space, 30 s CPU, 64 MB file size), a global concurrency semaphore, a 15 s default timeout and a 64 KB source cap.
- The source filter is regex-based, so treat it as defense in depth, not a boundary. The boundary is the sandbox.

### Outbound connections (read from the source, not captured from traffic)

The app has no account, no telemetry and no analytics endpoint: the hosts below are the only ones the code can contact, and each
needs a reason. A tool the app starts (`uv`, `git`, an agent CLI) makes its own connections as well.

- **This fork's repository on GitHub** (`api.github.com`, `raw.githubusercontent.com`, `github.com` archives): update checks, only
  while the updater is on (`DECOMP_UPDATES=off`, or an empty `REPO`, turns it off). Verified live: one URL.
- **Compiler and tool downloads**: the hosts named in `src/decompnet/toolchains.toml` (`github.com` releases, `files.decomp.dev`,
  `archive.archlinux.org`, `snapshot.debian.org`, `developer.arm.com`), sha256-pinned, only on `decomp setup`,
  `decomp toolchain install`, or when you ask the app to install one. `maintenance/tools/check_toolchains.py` checks them.
- **`uv`, PyPI and Astral**: the installer, once.
- **A project you choose to fork**: `git clone` of that repository, with its submodules, from whatever host it lives on. The app
  does not contact `decomp.dev` (the directory was retired; it lists what an earlier install saved).
- **The AI agent you connect**: the built-in API agent sends your prompts and the code it works on to the provider you configure
  (presets: DeepSeek, OpenRouter, OpenAI, or Ollama, LM Studio and llama.cpp on `127.0.0.1`). Agent CLIs (Claude Code, Codex and
  so on) use their own connections.
- **Team rooms**: when you host without giving an address, `cloudflared` (a pinned download) opens a `*.trycloudflare.com` quick
  tunnel; members connect to the host's address. Nothing else is sent anywhere.
- Other hosts that appear in the source are install hints (`nodejs.org`, `git-scm.com`, `adoptium.net`), documentation or product
  links, or identifiers inside text (`www.apple.com` in a plist DOCTYPE, `www.apache.org` in a licence header). Generated export
  READMEs and build scripts link this fork's repository (0.10.26).

## 10. Findings that matter for maintainers

Verified by reading the code:

1. **Updater and installers were hard-wired to the original author** (fixed in 0.10.10, 0.10.15 and 0.10.17). `app/updates.py` sets `REPO = "i12bp8/decomp.wtf"` and `SITE = "https://decomp.wtf"`. `install.sh`, `install.ps1`, `app/cli.py` (`--repo` default), the UI (`app.js` ~L351 and ~L2543, `index.html` ~L108) and the README all point there too. Any installed copy of your fork will offer to replace itself with upstream's code, or whatever that domain serves later. **This is the first thing to change.**
2. **The sandbox fell back to no sandbox** (fixed in 0.10.11). `compiler._sandbox_mode` returned `"none"` when `bwrap` was not installed; only `prlimit` remained, and agent-submitted C reached 1990s compilers with the user's privileges (demonstrated live: uid 0, host files readable). Now it refuses, with the explicit exceptions listed in the changelog. Note `trusted=True` does not mean "not agent code": exports compile matched agent C with it.
3. **Version coupling** (bounded in 0.10.12 to `mcp>=2.3.0,<3`). `mcp>=2.3.0` had no upper bound, and the code imports `mcp.server.mcpserver`, which is the 2.x API. `uv.lock` pins 2.3.0, but anything that installs without the lock can drift.
4. `rom/luvdis_run.py` patches the source of a third-party module at runtime (a string replace of `PUSH` with `SAFE_PUSH`, then `exec`). It used to break silently if luvdis changed (it ran unpatched and exited 0); since 0.10.27 it refuses unless the code is there exactly once.
5. The pinned toolchains download from external hosts (GitHub releases, `archive.archlinux.org`, `snapshot.debian.org`). They are sha256-pinned (no trust-on-first-use entries), but URL rot would break installs.
6. About 26 `except Exception` sites (audited in 0.10.29: 30 broad handlers in all, none on the path that decides a match; thirteen were silent, nine now log and four are allowlisted with a reason, enforced by a test). `grep` found no TODO/FIXME markers and no `shell=True`.
7. `compileall` over `src`, `tests`, `projects` and `site` succeeds, so there are no syntax errors on Python 3.12 (re-checked in 0.10.7).

Verified by running the code (0.10.7 baseline, see `baseline/README.md`):

8. **A fresh checkout fails 23 of 269 test items for reasons unrelated to the code under test.** `projects/demo/target/` does not exist after a clone (the `.o` files are gitignored, git does not keep empty directories, and `project.import_project` never creates the directory before running the build), which accounts for 21 items. Two more tests lack the skip gate their neighbours have. With the free toolchains installed the suite is 218 passed, 1 failed, 50 skipped; the one failure is the autopilot test's 60 s poll limit against a 70 s run on the test machine (a flake, not a defect).
9. **The skip gates under-specify what the tests need.** The demo-ROM build calls `llvm-objcopy`, but the gates check only `ld.lld`. Three `test_app_engine` tests need `m2c` and have no gate.
10. **Updater defaults (read, then confirmed in `app/server.py`):** the background watcher starts 20 s after launch and re-checks every 5 minutes, `check_updates` defaults to on, and `auto_update` (default off) installs without asking. The recorded `repo` in `install.json` overrides the `REPO` constant, so an install made by upstream's installer keeps pointing at upstream. `tests/conftest.py` sets `DECOMP_UPDATES=off`, which is how the suite avoids it.
11. **Installers fetched and ran code from upstream's network** (`site/public/install.sh`, `install.ps1`; fixed in 0.10.15). Their `VERSION` line names a wheel on a server; it must not be bumped unless that wheel exists.
12. The toolchain installer prints a raw Python traceback when a download host is unreachable (seen for `agbcc`, `ee-gcc-2.96`, `zlib.net`) instead of a one-line message.
13. **The fingerprint is not an identity** (fixed in 0.10.21). `FunctionObj.fingerprint()` hashes masked code and relocations as one
    unframed stream; three places decided a match by fingerprint equality alone, so a longer function with no relocations whose tail
    spells out the relocations' text was credited as a match (demonstrated through the real code; not reachable from C source compiled
    by the real toolchain). Now `same_as` compares directly, and hash-only paths also check the stored size. The relocation mask table
    (17 entries, 2,176 bit flips), the penalty ladder, and real gcc output (1,212 flips) were tested and are exact.
14. **A relocation inside undecodable x86 bytes crashed scoring** (fixed in 0.10.22). `scoring.disassemble` reads
    `ins.disp_size` on capstone's SKIPDATA pseudo-instructions, which raises, so `diff(f, f)` itself fails. Fails closed; x86 and
    x86-64 only.
15. **The database format was never versioned** (fixed in 0.10.31). Upstream wrote `PRAGMA user_version` = 0 into every database and migrated
    by adding columns in place, so code could not tell a database from the future from one it knew, and the first migration of an old
    database changed real work with no copy kept. Now: `SCHEMA_VERSION = 1`; a newer database is refused untouched; an older one is
    copied to `<file>.bak-v0` first. Opening an old database stays reversible: upstream's 0.10.6 opens a stamped one fine (verified).

Still open (needs your machine or a later change):

- PS2, GBA, DS, GameCube and Windows/WSL tests are skipped here. They need `ee-gcc-2.96`, `agbcc` plus the Arm GNU toolchain, the proprietary CodeWarrior compilers, and Windows. The sandbox could not reach `archive.archlinux.org`, `snapshot.debian.org`, `developer.arm.com` or `zlib.net`.
- The demo ROM needs zlib 1.1.4 from `zlib.net` (`projects/zlib-n64/prepare.py`, sha256-pinned). It was exercised here with an equivalent source (regenerated headers were byte-identical to the committed ones); run the real `prepare.py` on your machine.
- The GUI, the installers, and each platform pipeline end to end.

## 11. Responsible-use constraints worth keeping

The upstream README says to use only games you own, not to publish decompiled code, and to follow each public project's contribution rules, since many reject AI-written contributions. The code enforces part of this by never sending anything upstream. MIT covers the code. It does not cover the **name, domain or branding** "decomp.wtf", so a distributed fork should rename. Keep the LICENSE copyright notice.

## 12. Names

The product is called **Function_2_C_Decompiler** (owner's decision, 0.10.34). It was `decomp.wtf` upstream, and the original project keeps that
name wherever this fork credits it. What is called what:

| Thing | Name | Why it is what it is |
| --- | --- | --- |
| The product, wherever a person reads it | `Function_2_C_Decompiler` | The UI, messages, READMEs, agent prompts, generated files, commit messages, installer text. |
| Python package, import name | `decompnet` | Renaming it breaks every import, the lock file and every installed copy. |
| The command | `decomp` | The documented way to run it, in the agent skill and the installers. |
| Original project | `decomp.wtf` | Credit links to `github.com/i12bp8/decomp.wtf`, "upstream decomp.wtf", and (until the owner removed it in 0.11.5) its author's own notice in the README; his words are never rewritten. |

Kept **on purpose** because existing projects and installs depend on the exact string (each is pinned by `maintenance/tests/test_maint_naming.py`):
the project manifest `.decomp.wtf.json`; the `.decomp-wtf/` state folder and the `decomp-wtf` git branch the app creates in a fork; the WSL distro,
Docker container and volume, `/etc/decomp-wtf-runtime`, the systemd unit `decomp-wtf.service`; the Windows task `decomp.wtf` and the shortcut and
app-bundle file names (an uninstall must find what an old install made); the `/health` answer `"app": "decomp-wtf"` that processes recognise each other
by; the browser `localStorage` keys (renaming them resets every user's saved settings); the logger name `decomp.wtf`; and the plugin and marketplace
name `decomp-wtf` (`/plugin install decomp-wtf@decomp-wtf`). Renaming any of these is possible, but it is a migration (read the old name, write the new,
keep both working for a release) and not a find-and-replace.

How it was done: `maintenance/tools/rename_product.py` replaces the name in the files people read and **protects** the identifiers and credits above (a dry
run lists every change; a self-check refuses to run if its protection ever damages them). It does not touch `projects/`, because the demo builders write
a credit string into fixed-width ROM header fields (`b"...".ljust(40)` does not truncate, so a longer name would overflow the field and corrupt the
demo executable), nor the PowerShell installers (they refuse to run), nor `maintenance/` (history and documentation about upstream).

Known gaps: the README banner was replaced in 0.10.48 (source in `maintenance/assets/`), and the animated `demo.webp` had its title bar repainted in 0.11.4 (`maintenance/tools/repaint_demo_title.py`; its source is not in this repository); the demo ROMs carry the old
name in their embedded credit; and the sidebar layout for the longer name was made tolerant in CSS (smaller type, wrapping allowed) and then **checked in a real browser**
(0.10.37): `baseline/ui/desktop.png` and `phone.png` show the wordmark fitting at 1280 and 420 px.

## 13. Evaluating a model

`maintenance/tools/eval_agent.py` measures how well a model (or a prompt change) does on the bundled Demo Quest 64 ROM, through the same built-in API agent
the app uses. It imports the demo into a throwaway home, runs the autopilot (machine drafts from m2c matched for free: **20 of 95 functions**, the same 20 on every run),
then gives the first N still-open functions, smallest first, each to the model in its own fresh session told to work on that one function. It records per function: matched,
tool steps, tokens, dollars (only when the provider reports a cost), seconds, and any error. `--max-usd` is a hard cap (it reuses the project budget); functions skipped
for the cap are reported as skipped, not as failures. `--compare A.json B.json` shows what a change gained and lost.

What a result is, and is not:
- **One run is one sample.** Models are not deterministic; the function set and the free baseline are (verified: two runs gave the same 20 and the same functions), the model's
  answers are not. Repeat a run and look at the spread before believing a small difference.
- It measures matching the demo's functions, which are small. It says little about a 500-instruction function in a real game.
- The key is read from `EVAL_API_KEY` in the environment, never the command line (a `--api-key` is refused without echoing it), and never written to the result file.
- **The harness checks itself.** `--oracle` runs a scripted model that knows two answers through the real compiler and judge; it must match both, and exits 1 if it does not
  (so a broken harness is told apart from a bad model). A test makes it fail on purpose to prove the check can fail.
- Not yet done: a run against a real provider (it needs a key and money; the first one should be small, e.g. `--functions 3 --max-usd 1`).

## 14. Releasing

Written for a person who has never done it here. Nothing in this section has run on GitHub yet; the workflow's logic was rehearsed locally and `actionlint` passes.

1. Make the change on a branch, with its test. Bump the version with `python3 maintenance/tools/bump_version.py X.Y.Z` (it moves `pyproject.toml`, `__init__.py` and `uv.lock` together) and write the `## [X.Y.Z] - date`
   entry at the top of `maintenance/CHANGELOG.md`. That entry becomes the release notes word for word, so write it for a reader who was not here.
2. CI (`.github/workflows/ci.yml`) must be green. Among its checks, a step builds the wheel and `maintenance/tools/check_wheel.py` rejects an incomplete one (package data outside the package is the
   classic way to publish a wheel that installs and has no GUI) or one that ships tests, databases or settings.
3. Push a tag `vX.Y.Z` that matches the version exactly (`git tag vX.Y.Z && git push origin vX.Y.Z`). `.github/workflows/release.yml` then runs, and only on a tag (which only someone with write access can push): the `build` job
   (read-only token) checks the tag against the code and that the changelog has an entry, runs the tests, builds the wheel and the source distribution, checks the wheel, installs it into a clean environment from outside the
   checkout and runs it, and writes `SHA256SUMS`; the `publish` job (the only one with write access, and one that runs none of the repository's code) creates the release with the files, the checksums and the notes.
4. Anyone can check a download against the checksums: put `SHA256SUMS` beside the files and run `sha256sum -c SHA256SUMS`.

What a checksum does and does not give: it detects a damaged or truncated download. It does **not** prove who made the files, since someone who can replace the wheel can replace `SHA256SUMS` beside it. Proving that
needs signing with a key the owner holds. The plan keeps signing waiting for that. **How apps hear about a release (0.11.6):** the updater's `release` channel reads `VERSION=` from `site/public/install.sh` on `main` and installs the tag archive `vX.Y.Z` of this repository; the installer piped from curl installs the same archive; and `VERSION` is moved only by `set_install_version.py`, after the tag exists (steps in `maintenance/README.md`). Installing is from the tag's source archive, not the published wheel, and is not checksum-verified beyond GitHub's HTTPS. **The first release is 0.11.0, named ROMday** (the owner chose the name; the number is a plain PEP 440 one, since a name cannot be part of a version). A release can be named by its changelog heading, `## [0.11.0] - 2026-10-23 - ROMday`: the name is ordinary
words (letters, digits, spaces and `. _ ' -`, at most 40), becomes the GitHub release's title (`Function_2_C_Decompiler 0.11.0 - ROMday`) and is not part of the version or the tag. Most releases need no name.

One-time setup for the repository: switch on **private vulnerability reporting** (Settings, Code security), because the issue template's security link goes to that page and is a 404 until then.

