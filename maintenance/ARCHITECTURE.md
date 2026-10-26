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

- ~21k lines of Python in `src/decompnet`, ~5.5k lines in `tests/` (246 test functions, 269 collected test items once parametrized, in 38 files), plus a vanilla-JS front end (`app/static/app.js`), a marketing site (`site/`), installers (`site/public/install.sh|ps1`, `linux-base.sh`, `Dockerfile`) and a Claude Code plugin (`plugins/decomp-wtf`).
- Largest modules: `app/forkengine.py` 2396, `app/engine.py` 1730, `app/server.py` 1244, `app/agents.py` 1110, `app/collab.py` 844, `network.py` 779, `forks/scratch_dtk.py` 740, `app/twins.py` 694.
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
                    static/ (GUI), guide/ (agent knowledge base, ~20 markdown guides)
  server.py, registration.py, jobs.py, public.py, upstream.py, local.py, cli.py
                    LEGACY hosted-network layer (see section 8)
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

- **State:** SQLite via `store.py` (WAL, migrations inline) in `~/Decomp` (`$DECOMP_HOME`). Logs in `.decomp/logs/decomp.log`.
- **Team rooms:** `app/collab.py` and `forkroom.py`. One host hands out functions, verifies every match against its own copy, and shares only names, structs and notes. No ROM bytes or assembly cross the wire. Exposure is via a Cloudflare quick tunnel (`cloudflared` is a pinned toolchain) or your own address.
- **Platforms:** GameCube/Wii and N64 are "recommended". PS1, PS2, GBA and DS are beta. Windows runs inside its own WSL2 distro. macOS is unsupported.
- **Toolchains:** 25 registry entries (`toolchains.toml`) with sha256 pins on every download part. Proprietary ones (IDO 5.3/7.1, mwcc, mwccarm) are installed only after explicit license acceptance. Old 32-bit compilers run on a pinned i386 glibc runtime inside the sandbox.

## 8. Legacy hosted-network layer

`server.py`, `registration.py` (Cloudflare Turnstile signup), `jobs.py` (donated compute workers), `public.py` (website JSON), `upstream.py` (per-match git commits with credit), `local.py` (hash-only projects) and `cli.py` belong to an earlier design: a public coordinator at `api.decomp.online`. `.gitignore` says the hosted network was retired and its server scripts are "kept locally only". The code is still wired up (`decompnet/server.py` imports `jobs`, `policy`, `public` and `registration`; `decompnet/cli.py` imports `upstream` and `local`), and `cli.py` still defaults to `https://api.decomp.online`. The local app (`app/`) builds on `network.py` but does not need the web-signup, worker or public-page parts.

## 9. Security model (as implemented)

- The app listens on **127.0.0.1 only**. The GUI needs a per-launch secret (URL, then same-site cookie). Agents need bearer tokens, and MCP restricts allowed hosts and origins. Team rooms deliberately bind wider (`0.0.0.0` on a chosen port) when you host.
- Compiles run with `prlimit` (2 GB address space, 30 s CPU, 64 MB file size), a global concurrency semaphore, a 15 s default timeout and a 64 KB source cap.
- The source filter is regex-based, so treat it as defense in depth, not a boundary. The boundary is the sandbox.

## 10. Findings that matter for maintainers

Verified by reading the code:

1. **Updater and installers are hard-wired to the original author.** `app/updates.py` sets `REPO = "i12bp8/decomp.wtf"` and `SITE = "https://decomp.wtf"`. `install.sh`, `install.ps1`, `app/cli.py` (`--repo` default), the UI (`app.js` ~L351 and ~L2543, `index.html` ~L108) and the README all point there too. Any installed copy of your fork will offer to replace itself with upstream's code, or whatever that domain serves later. **This is the first thing to change.**
2. **The sandbox fell back to no sandbox** (fixed in 0.10.11). `compiler._sandbox_mode` returned `"none"` when `bwrap` was not installed; only `prlimit` remained, and agent-submitted C reached 1990s compilers with the user's privileges (demonstrated live: uid 0, host files readable). Now it refuses, with the explicit exceptions listed in the changelog. Note `trusted=True` does not mean "not agent code": exports compile matched agent C with it.
3. **Version coupling.** `mcp>=2.3.0` has no upper bound, and the code imports `mcp.server.mcpserver`, which is the 2.x API. `uv.lock` pins 2.3.0, but anything that installs without the lock can drift.
4. `rom/luvdis_run.py` patches the source of a third-party module at runtime (a string replace of `PUSH` with `SAFE_PUSH`, then `exec`). It breaks silently if luvdis changes.
5. The pinned toolchains download from external hosts (GitHub releases, `archive.archlinux.org`, `snapshot.debian.org`). They are sha256-pinned (no trust-on-first-use entries), but URL rot would break installs.
6. About 26 `except Exception` sites. `grep` found no TODO/FIXME markers and no `shell=True`.
7. `compileall` over `src`, `tests`, `projects` and `site` succeeds, so there are no syntax errors on Python 3.12 (re-checked in 0.10.7).

Verified by running the code (0.10.7 baseline, see `baseline/README.md`):

8. **A fresh checkout fails 23 of 269 test items for reasons unrelated to the code under test.** `projects/demo/target/` does not exist after a clone (the `.o` files are gitignored, git does not keep empty directories, and `project.import_project` never creates the directory before running the build), which accounts for 21 items. Two more tests lack the skip gate their neighbours have. With the free toolchains installed the suite is 218 passed, 1 failed, 50 skipped; the one failure is the autopilot test's 60 s poll limit against a 70 s run on the test machine (a flake, not a defect).
9. **The skip gates under-specify what the tests need.** The demo-ROM build calls `llvm-objcopy`, but the gates check only `ld.lld`. Three `test_app_engine` tests need `m2c` and have no gate.
10. **Updater defaults (read, then confirmed in `app/server.py`):** the background watcher starts 20 s after launch and re-checks every 5 minutes, `check_updates` defaults to on, and `auto_update` (default off) installs without asking. The recorded `repo` in `install.json` overrides the `REPO` constant, so an install made by upstream's installer keeps pointing at upstream. `tests/conftest.py` sets `DECOMP_UPDATES=off`, which is how the suite avoids it.
11. **Installers fetch and run code from the network** (`site/public/install.sh`, `install.ps1`). Their `VERSION` line names a wheel on a server; it must not be bumped unless that wheel exists.
12. The toolchain installer prints a raw Python traceback when a download host is unreachable (seen for `agbcc`, `ee-gcc-2.96`, `zlib.net`) instead of a one-line message.

Still open (needs your machine or a later change):

- PS2, GBA, DS, GameCube and Windows/WSL tests are skipped here. They need `ee-gcc-2.96`, `agbcc` plus the Arm GNU toolchain, the proprietary CodeWarrior compilers, and Windows. The sandbox could not reach `archive.archlinux.org`, `snapshot.debian.org`, `developer.arm.com` or `zlib.net`.
- The demo ROM needs zlib 1.1.4 from `zlib.net` (`projects/zlib-n64/prepare.py`, sha256-pinned). It was exercised here with an equivalent source (regenerated headers were byte-identical to the committed ones); run the real `prepare.py` on your machine.
- The GUI, the installers, and each platform pipeline end to end.
- Whether the legacy layer is used by anything you care about.

## 11. Responsible-use constraints worth keeping

The upstream README says to use only games you own, not to publish decompiled code, and to follow each public project's contribution rules, since many reject AI-written contributions. The code enforces part of this by never sending anything upstream. MIT covers the code. It does not cover the **name, domain or branding** "decomp.wtf", so a distributed fork should rename. Keep the LICENSE copyright notice.
