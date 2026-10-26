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

## [0.10.48] - 2026-10-22

**Docs, Tooling.** A new README banner, designed for this project (owner's decision), from a source that can be edited. Nothing under `src/` changed.

- **The banner is new.** The old one was upstream's artwork: its wordmark (`decomp.wtf`) and its tagline ("What the function?"). The new one puts the project's name first, set the way the app sets it: `Function_2_C_` over a green
  `Decompiler`. Beside it is a card that shows the product's idea in one look: real matching C, the demo ROM's `player_take_damage`, with a **score 0 · byte-identical** badge and a strip of functions turning green.
  The platform chips mark the three recommended platforms the way the README's table does. It uses the app's own colors and fonts (Geist and Geist Mono, SIL OFL, already shipped), so it looks like the product. Light
  and dark versions, 2560 x 800 (345 KB and 285 KB), served by the README's existing `<picture>`. I looked at both renders and changed two things I did not like in the first one: the strip of functions
  overlapped the end of the code (lines 10 and 11 were cut off), and the tagline ran into the chips.
- **It is editable.** `maintenance/assets/banner.html` is the source (one file, a theme switch in the URL hash); `maintenance/tools/make_banner.py` renders both PNGs with a headless Chromium (`CHROME=...`),
  and `maintenance/assets/README.md` says how. The code in the card is from the demo, which is CC0.
- The README's alt text is now the project name and the banner's own tagline. 12 tests in `test_maint_banner.py`: both files are PNGs of the expected size and under 600 KB; **neither is upstream's artwork** (checked
  by hash, which is what catches it: upstream's banner has the same dimensions); the `<picture>` serves dark to dark mode; **the alt text equals the source's tagline** (an image's words are invisible to a
  screen reader, so the alt text is all those readers get); the source spells the name as the app does and never as the original; its fonts exist and are the app's; its palette is the app's; the render command
  is right; and, with a browser, the real render gives both banners at the right size. Four breakages (the old alt text, the tagline edited without the README, **upstream's banner restored**, the dark
  source pointing at the light file) each turn exactly one test red.
- **Still showing the old name, found by looking:** `.github/assets/demo.webp`, the animated recording of the live view in the README, has `decomp.wtf / Demo Quest 64` in its title bar. It is a recording, so it
  cannot be edited frame by frame; fixing it means re-recording the animation, which is a separate piece of work (say if you want it). `how-light.png` and `how-dark.png` (the "How it works" diagram) carry no product name.
- Nothing for users to do.

## [0.10.47] - 2026-10-22

**Feature.** A provider-aware budget (owner's decision): prices per endpoint, so OpenAI's and DeepSeek's spend counts; every charge logged by provider, agent and model; one global cap that
counts everything together; subtotals in the app. (Plan Phase 3, item 1: the part I had left for you to decide.) Schema version 2.

- **Prices on an endpoint.** Three optional fields on the agent form (and in the saved endpoint): input, output and cached-input price, in US dollars per million tokens. With an input and an output
  price, a request's cost is computed from the token counts the provider reports; with only one, nothing is computed (the other half would silently be free). **Cached tokens are priced at their own rate**
  because both providers discount them and report them differently: OpenAI in `prompt_tokens_details.cached_tokens`, DeepSeek in `prompt_cache_hit_tokens`; without a cached price they cost the input rate,
  and a cached count larger than the prompt is capped so it cannot make the uncached count negative. **What the provider itself reports (OpenRouter's `cost`) still wins**, as in 0.10.39. A bad price
  (text, negative, NaN, infinity, a boolean) is refused with "a price is a number of US dollars per million tokens, like 0.27" and changes nothing; 0 or empty clears it. No prices are built in: they change,
  and a stale default would make the budget quietly wrong.
- **A log, not just totals.** New table `spend_log` (project, time, **provider, agent, model**, dollars, tokens), in the same transaction as the project's running totals, so the log always adds up to them. The tags
  are stored, so any later breakdown (by day, by model) needs no migration. A custom server is tagged by its name (`gpu-box`), not by the word "custom"; a command-line agent by its kind (`claude`, `codex`...).
  `add_spend` keeps working without tags (upstream's own test calls it that way); such a charge, and everything spent before this version, shows as **untagged**, never hidden: the subtotals plus untagged always equal the total.
- **One global cap.** The budget is still one number and `over_budget` still reads the total, so it crosses when the providers *together* do (0.6 on one plus 0.5 on another stops a 1.0 cap although neither is over).
  Per-provider caps were not asked for and are not built.
- **In the app.** The overview reads, for example, "$4.71 spent (Claude Code $2.20 · OpenAI $1.95 · DeepSeek $0.31 · earlier $0.25) · cost per match · budget $8.00" (checked in the real GUI with seeded data and a
  screenshot of the Agents and models page showing the price fields filled in). The overview API carries `spend_by` (providers, each with its agents and models).
- **Schema version 2** (`SCHEMA_VERSION = 2`): a version-1 database gains the empty table on open, keeping its `.bak-v1` copy first, as in 0.10.31; upstream's 0.10.6 database does too. Reversible: upstream's own code
  opens a version-2 database and ignores the table.
- Tests: 33 in `test_maint_spend_by_provider.py` (cost computation in both providers' styles, every unusable price and token count, provider's figure wins, the tagged log and its totals together, untagged charges, subtotals,
  the global cap across providers, tag normalisation, price saving and refusal, session options, two priced sessions through the real agent loop giving the right subtotal each, a custom server's tag, a
  command-line agent's tag, the GUI's fields). The schema tests' comparison helper now ignores tables a migration adds.
- **A bug the Python tests could not see, found by running the real thing:** my first GUI edit declared `const names` twice in one function, which stops the whole GUI script from loading, and all 135 Python tests passed because they only read
  `app.js` as text. `node --check` caught it. New `test_maint_gui_js.py` runs that syntax check on every script the GUI ships whenever Node is available, and is shown to fail on exactly that mistake.
- Not done: per-provider caps; entering prices from a provider's own price list (they would go stale); a history chart. The first of these is a one-line change to compare a provider's subtotal if you want it.
- Verified here: the spend, agent, server, bridge, schema and GUI tests; the whole suite runs at the next checkpoint.
- Nothing for users to do. Prices are optional: add them on the Agents and models page.

## [0.10.46] - 2026-10-22

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run L** in `maintenance/baseline/`: the maintained code at 0.10.45, measured the same way, **with `BUILD_WHEEL=1`** so the test that builds and checks the real wheel runs and passes (without it that one test is
  skipped): **617 passed, 0 failed, 53 skipped (670 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run K fails; against K, 43 items are
  new (all pass) and 1 is gone: the CI guard test I renamed when I narrowed it (`test_no_workflow_uses_secrets_or_writes_to_the_repository` became
  `test_no_workflow_uses_secrets_or_pushes_and_only_the_release_workflow_may_write_at_all`, which is present and passes). The bare-machine CI commands, now including the wheel build and check:
  516 passed, 154 skipped, 0 failed; `actionlint` on both workflows: clean.
- `MAINTENANCE_PLAN.md`: status as of this version. Phase 4: the release workflow, the wheel check and the issue template are done; signing and the update channel are not, and the first release's number is yours.
- `maintenance/patches/`: regenerated, 40 patches (0.10.7 to 0.10.46).
- Nothing for users to do.

## [0.10.45] - 2026-10-22

**Tooling, CI.** A release workflow with checksums, a wheel checker, and a bug-report issue template that matches the app. (Plan Phase 4: "release wheels built by CI, with
checksums published next to them" and "an issue template that matches the app's Copy for a bug report output".) Nothing under `src/` changed.

- **`.github/workflows/release.yml`**: pushing a tag such as `v0.10.45` builds the wheel and the source distribution, checks them, and publishes a GitHub release whose notes are that version's
  changelog entry, with a `SHA256SUMS` file beside the downloads (`sha256sum -c SHA256SUMS`). Two jobs so the one that runs code is read-only: `build` (read-only token) checks that the tag equals the
  version in the code and that the changelog has an entry for it, runs the tests, builds, checks the wheel, **installs the wheel in a clean environment from outside the checkout and runs it**, and writes
  the checksums; `publish` is the only job with write access and runs no code from the repository: it downloads what `build` made and runs `gh release create --verify-tag`. Nothing else triggers it.
  All four actions are pinned by full SHA (`download-artifact` v8.0.1, seven months old, chosen over the 15-day-old v8.0.2 for a workflow that holds release-writing permission; the SHA CI already pins for
  `upload-artifact` v7.0.1 was confirmed against GitHub's real tag). **Not run on GitHub** (I cannot): `actionlint` is clean, and I rehearsed the build job here by running its `run:` steps in order, from the YAML itself, with GitHub's variables and its default `bash -e` (the lock install and the full suite skipped, as they are run separately). With a good tag every step passed and `release/` held the wheel, the source distribution, `SHA256SUMS` (listing both, and verifying) and the notes; **a wrong tag stopped it at the first step** with the `::error::` line; **a missing changelog entry stopped it** with exit 2. The clean-environment install fetched the wheel's dependencies from PyPI and ran. Adding one byte to the wheel makes `sha256sum --check` fail.
- **The existing CI guard narrowed, not weakened.** `test_maint_ci_workflow.py` forbade `contents: write` in every workflow. Now exactly one file, `release.yml`, may have it, and
  `test_maint_release_workflow.py` pins how (8 tests): triggers only on a pushed tag; read-only default token; write permission on the `publish` job alone, which has no checkout and runs only
  `gh release create`; no unpinned action; credentials not persisted; the tag/tests/wheel/checksum steps all present; the wheel installed from outside the checkout. Six dangerous edits (write access
  on `build`, a checkout in `publish`, a `pull_request` trigger, the wheel check dropped, a movable tag, write access in `ci.yml`) were each applied in turn: **every one turns a test red.**
- **`maintenance/tools/check_wheel.py`** (also a new CI step, so a broken wheel shows up on every push and not at release time): what a wheel must contain and must not. It lists the files the app cannot
  run without (the GUI page and scripts, the compiler registry, the demo ROM, the Ghidra script, 20+ agent guides), the `decomp` entry point, the LICENSE and the metadata (name and version), and rejects
  tests, docs, projects, caches, databases, settings and env files. The real wheel built from this tree passes (121 files, 644 KB), and **installed alone into a clean virtual environment it runs from outside
  the source tree**: `decomp --help` works and the package finds its own GUI, 21 guides, registry and demo ROM. 25 tests (a broken wheel for each defect: a missing GUI file, a stray `tests/`, a wrong
  version, no entry point, no license, too few guides, not a zip); one builds the real wheel and runs when `BUILD_WHEEL=1` (it passes).
- **`maintenance/tools/release_notes.py`**: prints one version's changelog entry for the release notes, and exits 2 with nothing on stdout if there is none, so a release can never go out with
  someone else's notes or none. (A test also checks the real changelog has notes for the version in `pyproject.toml`.)
- **`.github/ISSUE_TEMPLATE/bug_report.yml` and `config.yml`.** The app has one bug-report flow: when an import fails it shows **Copy for a bug report**, which copies `Importing:`, `Error:` and a fenced `Log:`.
  The form tells people to press exactly that button, to fall back to the **What happened** text if the clipboard is unavailable (the same fallback the app's own message gives), requires the report, and asks
  for the kind of game and the agent. It does not set `render:` on the report field, because the report contains its own code fence and GitHub would wrap the paste in a second one. It requires two boxes
  (no game file, disc image or commercial code attached; nothing private pasted), in line with the responsible-use constraint. `config.yml` points security reports at a private page of this repository
  (that page is a 404 until you switch on **private vulnerability reporting** in the repository settings). 9 tests read the app's own HTML and JS and hold the template in step in both directions; five edits to
  the app and the template (renaming the button, adding `render:`, dropping the `Error:` line, the app dropping its `Log:` line, making the no-game box optional) each turn one red.
- Verified here: the release-tool, workflow and template tests; `actionlint` on both workflows; the wheel built and installed. The whole suite runs at the next version.
- **For you:** this does nothing until it is on GitHub: push, then to release, bump the version (`maintenance/tools/bump_version.py`), write the changelog entry, commit, and push a tag `v<version>`. Switch on
  private vulnerability reporting for the security link. Version numbers stay as they are (`0.10.x`); whether the first public release should be named differently (the plan suggested `0.11.0-fork.1`, which
  PEP 440 does not allow as written) is yours to decide.
- Not done: signing the releases. Checksums beside the downloads tell you the files were not corrupted; they do not prove who made them, because an attacker who can replace the wheel can replace
  `SHA256SUMS` too. Signing needs a key you hold and a decision on where it lives, and the plan rightly makes an update channel wait for it. `decomp update` is unchanged.

## [0.10.44] - 2026-10-22

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run K** in `maintenance/baseline/`: the maintained code at 0.10.43, measured the same way: **575 passed, 0 failed, 53 skipped
  (628 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run J fails; against J, 27 items are
  new (the backup tests, all pass) and none is gone. The bare-machine CI commands: 475 passed, 153 skipped, 0 failed; `actionlint` on the workflow: clean.
- `MAINTENANCE_PLAN.md`: status as of this version. Phase 3 item 6 says what is done (backup and restore) and what is not (resume after a crash; the headless run mode).
- `maintenance/patches/`: regenerated, 38 patches (0.10.7 to 0.10.44).
- Nothing for users to do.

## [0.10.43] - 2026-10-22

**Feature.** `decomp backup` and `decomp restore`: a safe way to keep a copy of your project work. (Plan Phase 3, item 6, the backup half.) New `app/backup.py`, two
subcommands in `app/cli.py`, a README line. Nothing existing changed.

- Your work (matches, attempts, notes, names) is one SQLite file, `~/Decomp/.decomp/decomp.db`, and there was no supported way to snapshot it. **`cp` is not safe**: while the
  app runs the database is in WAL mode, so committed work can still be only in the `-wal` file, which a copy of `decomp.db` misses. A test shows it, not assumes it: a note committed
  through an open `Store` is in the backup's snapshot and absent from a plain file copy of the same database.
- `decomp backup [DEST] [--force]`: a consistent snapshot through SQLite's online backup API, safe while the app is running and writing. The live database is opened query-only.
  The snapshot is written under a temporary name, **verified (a SQLite file, `integrity_check` ok, our tables, a format version this build understands) and only then renamed**, so a failed run
  never leaves something that looks like a backup. DEST can be a file or a folder (it gets a timestamped name); the default is `<home>/backups/decomp-backup-<time>.sqlite`. An existing file
  is never overwritten without `--force`, and backing up onto the live database is refused. It prints what it holds ("Backed up 1 project, 95 functions (0 matched), 0.7 MB") and what it does not.
- `decomp restore FILE [--yes]`: refuses while the app is running (replacing a database under a live connection corrupts it); without `--yes` it only says what it would do. It works on a **copy** of
  your backup (the file you give it is only ever read: its hash is unchanged), verifies that copy before touching anything, keeps the database it replaces as
  `decomp.db.before-restore-<time>` (never over an earlier one: a second restore in the same second gets `-2`), deletes stale `-wal`/`-shm` files, then swaps. A backup from a newer version, a
  file that is not a database, and a damaged copy are each refused with a reason, and the current database is left exactly as it was.
- **What it holds, and does not:** the project database. API keys and settings are in `settings.json`, so a backup can be shared without leaking them. Game files and forked projects' git repositories are
  yours and already live elsewhere. The command says so every time.
- Tests: 27 in `maintenance/tests/test_maint_backup.py`, found to be able to fail by **mutation checks** (each of four breakages of the module was applied in turn): a naive file copy fails 3 tests;
  ignoring a running app fails 2; skipping verification fails 1; and removing the stale-`-wal` cleanup **failed none**. The check caught that my first test for that was vacuous: restoring first snapshots the old
  database to keep it, and opening and closing a database makes SQLite tidy its own sidecar files, so the test's stale files were gone before the cleanup ran. A second test now uses orphaned
  sidecars with no database beside them, which only the cleanup removes, and the mutation fails it. (So in the ordinary case SQLite already tidies up; the explicit deletion covers orphans and is defense in depth.)
- **Against the real app, with the demo project:** `decomp backup` while the app was running worked; `decomp restore --yes` while it was still running was refused with the error line and changed nothing;
  after `decomp stop` the restore succeeded, reported where the replaced database was kept, and the restored database opened in `RomNetwork` with its 95 functions.
- Verified here: the 27 backup tests pass; lint clean. The whole suite runs at the next version.
- Not covered: automatic backups (they cost disk without asking, and a big game's database is large: say if you want a rolling daily one); backing up `settings.json` (it holds keys; copy it yourself if you
  want it); resume after a crash and the headless run mode, the other two items under plan Phase 3 item 6.
- Nothing for users to do. Try `decomp backup`.

## [0.10.42] - 2026-10-22

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run J** in `maintenance/baseline/`: the maintained code at 0.10.41, measured the same way: **548 passed, 0 failed, 53 skipped
  (601 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run I fails; against I, 18 items are
  new (the eval-harness tests, all pass) and none is gone. The bare-machine CI commands: 448 passed, 153 skipped, 0 failed; `actionlint` on the workflow: clean.
  (A first full run of this tree showed three tests as skipped that had passed before: the ROM-order artifact of cleaning the build outputs, not a regression. It
  was rerun after rebuilding the ROMs, and run J is that rerun.)
- `MAINTENANCE_PLAN.md`: status as of this version. Phase 3 item 1 is done except for a run against a real provider, which needs your key.
- `maintenance/patches/`: regenerated, 36 patches (0.10.7 to 0.10.42).
- Nothing for users to do.

## [0.10.41] - 2026-10-22

**Tooling.** An eval harness: measure how well a model, or a prompt change, does on the demo ROM. (Plan Phase 3, item 1, the rest of it.) New
`maintenance/tools/eval_agent.py`; nothing under `src/` changed. ARCHITECTURE section 13 says what it does and, more to the point, what a result is not.

- How it measures: imports the demo into a throwaway home, runs the autopilot for the **free baseline (20 of 95 functions, the same 20 on both runs I made, and
  the same first functions chosen after it)**, then gives the first N open functions, smallest first, each to the model in a fresh session told to work on that one
  function only. Per function it records matched, tool steps, tokens, dollars (when the provider reports a cost), seconds and any error. `--max-usd` is a hard cap
  built on the 0.10.39 budget check; functions skipped for it are reported as skipped, never as misses. `--compare A.json B.json` shows what a change gained and lost.
- **It checks itself.** `--oracle` runs a scripted model that knows two answers through the *real* compiler and the real byte-for-byte judge: it must match both
  (2 steps each, exit 0), and it exits 1, saying the harness is broken and not a model, if it does not. A test makes it fail on purpose (a compiling but wrong answer)
  and asserts the failure is that, not a crash. No key and no network are needed for any of this.
- Bugs found by running it, all fixed (each is now pinned by a test): a capital-W/lower-case mismatch made the first oracle run answer "I don't know" to everything (the
  self-check caught it on its first run); `--functions`' default shadowed the oracle's own set; the baseline line printed "autopilot matched 0" when it had not been run;
  a spending-cap message read "$0.00" for a $0.0025 cap; a function skipped for the cap was being counted as a miss by the exit rule; and, worst, **the scripted model was
  installed by patching `httpx.Client` globally and never removed**, so a second call in one process wrapped the first and threw. That also meant my first "the self-check
  can fail" test passed *because of that crash*, not because of the wrong answer it was written to detect. Now the patch is scoped to the run, the test asserts the
  wrong answer was compiled and judged a miss (steps 2, no error), and a mutation check (putting the leak back) makes the relevant tests fail.
- A key can never be given on the command line: argparse accepts an unambiguous prefix, so `--api-key sk-...` had been read as `--api-key-env sk-...`, and the pasted
  secret was **printed back in an error message** as a missing variable's name. Abbreviations are off, `--api-key` is refused outright without repeating its value, and the key is
  read from `EVAL_API_KEY`. The result file keeps the endpoint's host only: a test feeds it a URL with a password and a `?key=` and checks neither appears.
- Tests: 18 in `maintenance/tests/test_maint_eval_harness.py`: the ordering, the oracle's script, the summary and report (a summary of nothing does not divide by zero), `--compare`,
  the key rules, and, where the compiler and sandbox exist (they do here), the oracle matching 2 of 2, the deliberate failure, a miss, the cap, an unknown function, and
  two runs in one process leaving no patch behind. Verified here: those 18 pass.
- **Not done, and not claimable:** a run against a real provider. That needs your key and costs money, and provider behaviour (tool-call formats, cost reporting,
  rate limits) is exactly what a scripted model cannot show. Start small: `EVAL_API_KEY=... uv run python maintenance/tools/eval_agent.py --base-url ... --model ... --functions 3 --max-usd 1`.
- Nothing for users to do.

## [0.10.40] - 2026-10-22

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run I** in `maintenance/baseline/`: the maintained code at 0.10.39, measured the same way: **530 passed, 0 failed, 53 skipped
  (583 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run H fails; against H, 49 items are
  new and none is gone. All but one of the new ones pass; the one that does not is the screenshot-tool test that needs `CHROME=<a browser>`
  (it passed when a browser was supplied, in 0.10.37). The bare-machine CI commands: 436 passed, 147 skipped, 0 failed; `actionlint` on the workflow: clean.
- `MAINTENANCE_PLAN.md`: status as of this version. Phase 3 item 1 says how far it got (retries done, the cost cap done for providers that report a
  cost, the eval harness not started) and what is left for you to decide (per-agent prices).
- `maintenance/patches/`: regenerated, 34 patches (0.10.7 to 0.10.40).
- Nothing for users to do.

## [0.10.39] - 2026-10-22

**Fix.** The project budget can now stop the built-in API agent, and does so in the middle of a session. (Plan Phase 3, item 1, second half:
"cost caps per project".) Touches `app/agents.py` and one line of text in the Settings screen.

- The problem: the budget is in US dollars and was fed only by agents that report dollars (Claude Code and the like). The API agent recorded
  `{"tokens": ...}` and nothing else, so its spend stayed at **$0 and the cap could never fire for exactly the agents that bill per token**. And the
  cap was only looked at between sessions, so one session of up to 120 steps could spend past it.
- Now: **the cost a provider reports is recorded in dollars** (OpenRouter puts `cost` in every response's `usage`; that is the common case that needs no
  configuration), and **the budget is checked before every request**: when it is spent the session ends with "the project's budget is spent" in the agent's
  feed, and the run loop then stops the agent with its existing message. A session can overshoot by at most the one request in flight.
- The cost is never trusted blindly: only a real, positive, finite number counts. A string, `null`, a negative, NaN or infinity, a list, and **a JSON
  boolean** are ignored (Python's `float(True)` is 1.0, so a naive parse would book a dollar for a provider that sent `"cost": true`).
- **What this does not do, and the Settings label now says so:** a provider that reports no cost (OpenAI's own API, DeepSeek) is unchanged: tokens are
  recorded and the dollar budget does not apply to it. Making it apply needs prices entered per agent (two numbers on the agent form, carried through the save
  endpoint and the session options), which is a feature to decide on, not to slip in; it is left open in the plan.
- Tests: 19 in `maintenance/tests/test_maint_api_agent_budget.py`. **5 fail against the previous code** (measured): cost recorded, cost recorded without a
  token count, the budget ending a session mid-way (3 requests at 2 cents against a 5-cent budget), the same with no budget running to its end, and a
  budget already spent stopping before the first request. The other 14 pin what must not change (tokens-only providers; bad costs ignored; no budget means no
  limit; a dollar budget does not stop a provider that reports no cost). **Against a real socket:** a provider reporting 2 cents a request and a 5-cent budget
  sent 3 requests, recorded $0.06 and 3,000 tokens, and ended the session with the message.
- Verified here: the budget, retry, agent, server, bridge, naming, links and release-hygiene tests (120 passed, 1 skipped); lint clean; `app.js` parses. The whole suite runs at the next version.
- Nothing for users to do. Set the budget in Settings as before.

## [0.10.38] - 2026-10-22

**Fix.** The built-in API agent retries a request in place, so a blip between the app and the model's server no longer costs it the
conversation. (Plan Phase 3, item 1, first half: "retries and backoff in the built-in API agent".) Touches `app/agents.py` and one upstream test.

- What the plan said was missing was partly there already: throttling (429 and rate-limit wording) is detected and waited out at the session
  level, "no credit" is fatal, an over-long request is trimmed and resent, three failures in a row stop an agent, and a budget cap exists. What was
  really missing was at the level of the single request. `client.post(...)` was not guarded, so a connection reset or a timeout raised out of the
  loop, and a 502/503/504 returned "failed"; either way **the conversation was thrown away**, the turn counted as a failure (three in a row stop
  the agent), and a 429 restarted the whole session a minute later.
- Now `post_with_retries` sends the request again, in the same conversation, after a wait, when the failure is plausibly transient: a connection
  error or timeout, or a 429, 500, 502, 503 or 504. Up to 5 tries, waiting 2, 4, 8, 16 seconds, or what the server's `Retry-After` asks, never more than
  two minutes. The agent's feed says what is happening ("the model's server said 503: trying again in 2s"). Stopping the agent ends the waiting. After
  the last try the last answer or the network error comes back exactly as before, so everything downstream (the session-level throttle wait, the three
  failures rule) is unchanged.
- **Never retried**, because retrying cannot help: a bad request, a refused key, a missing model (400/401/403/404), payment required (402), "out of
  credit" (OpenAI reports that as a 429 `insufficient_quota`), and "context too long" (some servers report that as a 500, and the existing code
  trims and resends those itself). Eight such cases are pinned.
- **A server on this computer that is not running fails at once.** Retrying a refused connection to `127.0.0.1` cannot start Ollama, and without
  this the user would wait about 30 seconds per session to be told so. `is_local` decides (it counts any dotless host name, such as a docker-compose
  service called `ollama`, as local); a *busy* local server (llama.cpp answers 503 while it loads a model) is still retried. Found while testing:
  my first tests used a made-up host `mock`, which `is_local` treats as local, so they used a public address literal instead.
- Tests: 23 in `maintenance/tests/test_maint_api_agent_retry.py` (the helper alone with a scripted server and a fake clock; then through the real
  agent loop: one 503 and one connection reset in the middle of a session now leave a single conversation sent three times, no error, and a feed
  that says so. **22 of the 23 fail against the previous code** (measured by running them against it); the 23rd is a guard that a server
  that stays down is still reported as before). **Against real sockets and a real clock:** a
  throwaway HTTP server answering 503 twice with `Retry-After: 0.3` was retried at exactly 0.3 s intervals and then succeeded; a real refused
  connection to a local port raised in 27 ms.
- One upstream test adapted: `test_builtin_api_agent_out_of_credit` scripted one 429 and then a 402 as two separate sessions; a 429 is now retried
  in place, so it scripts a *persistent* 429 (`RETRY_ATTEMPTS` of them) for the first session, with a fake clock so no test sleeps. Its intent is
  unchanged: a throttled session is not a failure, and the next session meets the fatal no-credit.
- Verified here: the agent, server, bridge and retry tests (51 passed), lint clean; the whole suite runs at the next version.
- Behavior to know about: a remote provider that is down now takes up to about 30 seconds per session to report it, instead of failing at once.
- Nothing for users to do.

## [0.10.37] - 2026-10-22

**Tooling, Docs.** The sidebar layout, the one thing the rename (0.10.34) left unverified, is now checked in a real browser, and the
way to do that is a tool. No change under `src/`.

- **Verified by looking.** The product name is 23 characters where the old one had 10, in a 248 px sidebar. I could not see it in 0.10.34, so
  I made the CSS tolerant and said so. A real browser is obtainable here (the portable `ungoogled-chromium` 155.0.8059.84-1 from GitHub
  releases; **its sha256 matched the digest GitHub shows for that asset** before it was run, and it only ever loaded the app's own localhost
  page). Result: at 1280 px the wordmark `Function_2_C_Decompiler`, with `Decompiler` in green, sits inside the sidebar with room to spare; at 420 px
  the narrow header shows the menu button, the logo and the whole name on one line. Nothing overflows or wraps. The screenshots are kept in
  `maintenance/baseline/ui/`.
- New `maintenance/tools/screenshot_ui.py`: starts the app on a free port with a throwaway home and updates off, loads it headless at both widths,
  writes `desktop.png` and `phone.png`, and stops the app by its process id. Needs `CHROME=<a Chromium binary>`; a browser is not a dependency.
  Tests (4 in `test_maint_screenshot_tool.py`): the command it builds and its two widths, a polite refusal without a browser, and, only when
  `CHROME` is set, a real run that takes both screenshots and leaves no app process behind. All four pass here with the browser; three pass
  without it.
- Still showing the old name, found by looking at it: the README banner image (`.github/assets/banner-light.png`) shows the wordmark
  `decomp.wtf` and upstream's tagline "What the function?" beside the README's new alt text. It is artwork, so replacing it is your call; the
  documents now say exactly that instead of "banner images".
- Two stale statements in the plan corrected (the rebrand was still listed as an open decision, and the tools table in this folder's README missed
  three tools).
- Nothing for users to do.

## [0.10.36] - 2026-10-21

**Fix, CI.** The rename tool and its tests work in an unpacked zip. Found by the cold-start check of the 0.10.35 zip; **that zip had the
defect** (two tests fail when the suite is run from it), and this version replaces it. No change under `src/`.

- The problem: `maintenance/tools/rename_product.py` listed files with `git ls-files`, which exits 128 ("not a git repository") in an
  unpacked zip. So `test_no_covered_file_still_has_the_old_name_outside_a_protected_span` and
  `test_every_credit_link_to_the_original_project_is_intact_and_none_is_damaged` errored for anyone who unzipped the delivery and ran the
  suite. (They had passed in my working tree and in every run, which is why only the cold start from the actual zip showed it.)
- A quieter variant, fixed with it: unpacked *inside another git repository* (say, copied into a clone before committing), `git ls-files`
  succeeds and names nothing for these untracked files, and the checks would then **pass over zero files**. The file list now falls back to
  walking the folder when git cannot answer, or answers with nothing under `src/`, and a test asserts it is never empty.
- Tests: 3 new in `test_maint_naming.py` (2 failed before): the list works without git and has the same scope as with it; it is never empty when
  git lists nothing here; the checks look at a real number of files. Also run in a copy made like the zip, with the real interpreter: 32 passed.
- **CI now proves it every time:** a step in the `checks` job runs `maintenance/tests` from an unpacked `git archive HEAD`, which has no
  `.git`, in its own environment (`uv sync --locked`). Its commands were run here exactly as written, with `RUNNER_TEMP` set as GitHub sets
  it: 272 passed, 2 skipped, no `.git`. `actionlint` is clean, and the workflow guard test requires the step. `CLAUDE.md` gains the rule: tests and
  tools must work in an unpacked zip.
- Verified: **whole suite with every tool: 485 passed, 0 failed, 52 skipped (537 items)**; test by test, nothing that passed in run H fails and nothing is gone, and the 3 new tests pass.
  The bare-machine CI commands: 391 passed, 146 skipped, 0 failed. The delivered zip was then unpacked fresh and its whole suite, run from there, passes.
- `maintenance/patches/`: regenerated, 30 patches (0.10.7 to 0.10.36).
- Nothing for users to do.

## [0.10.35] - 2026-10-21

**Docs.** Status, the final measurements for this pass, and the patch set. No change to the application.

- **Run H** in `maintenance/baseline/`: the maintained code at 0.10.34, measured the same way: **482 passed, 0 failed, 52 skipped
  (534 items)** with every free tool and `bwrap`. Test by test, nothing that passed in upstream's run C or in run G fails; against G,
  29 items are new (the naming tests, all pass) and none is gone. The bare-machine CI commands: 388 passed, 146 skipped, 0 failed in 14 s; `actionlint` on
  the workflow: clean.
- `MAINTENANCE_PLAN.md`: status as of this version (item 1.1 is done, with the named exceptions). `README.md` (this folder's index) and the
  patches README are updated.
- `maintenance/patches/`: regenerated, 29 patches (0.10.7 to 0.10.35).
- Nothing for users to do.

## [0.10.34] - 2026-10-21

**Rename.** The product is called **Function_2_C_Decompiler** wherever a person reads it (owner's decision). Its identifiers, and the
original project's own name, are left exactly as they were. (Plan item 1.1, the staged rebrand.) 64 files changed, 715 insertions, 377 deletions.

- Why this was not a find-and-replace: the string `decomp.wtf` appeared in about 700 places and they were three different things: **the product's
  name** (renamed), **identifiers existing projects and installs depend on** (kept), and **the name of the original project** wherever this fork
  credits it (kept). The new `maintenance/tools/rename_product.py` does the renaming with the other two protected (dry run by default, a
  self-check that refuses to run if its protection ever damages what it protects). It changed 352 lines in 54 files: the app, the GUI and its
  page title and wordmark, CLI help and messages, agent prompts, the MCP server's title, generated READMEs and commit messages, installer text,
  the plugin and its skill, the README.
- **Kept on purpose** (pinned by tests): the project manifest `.decomp.wtf.json`; the `.decomp-wtf/` folder and `decomp-wtf` git branch the app
  creates in forks; the WSL distro, Docker container, `/etc/decomp-wtf-runtime` and systemd unit names; the Windows task and shortcut file names; the
  `/health` answer `"app": "decomp-wtf"` that processes recognise each other by; the browser `localStorage` keys (renaming resets everyone's saved
  settings); the logger name; the plugin and marketplace name. The package stays `decompnet` and the command `decomp`. See ARCHITECTURE section 12.
- Things a rename tool would have broken, found by reviewing its output before applying it (I reviewed all of it in two passes):
  1. **The original author's own notice** in the README ("I've decided to stop working on decomp.wtf and archive it") would have become Sam Wolfs
     announcing the end of *this* project in the new name. Protected, and a test pins his words.
  2. **A credit link would have been rewritten into a dead one**: my first protection pattern covered `[decomp.wtf](https://github.com/i12bp8` but
     not the `/decomp.wtf)` after it, so the upstream URL would have become `.../i12bp8/Function_2_C_Decompiler`. Fixed, with a built-in check
     and a test that no upstream URL is damaged.
  3. **Demo ROM credits**: `projects/demo-psx/build.py` writes `b"Demo Quest PS1 - made for decomp.wtf".ljust(40)` into a 40-byte header field. The
     new name makes it 49 bytes, and `ljust` does not truncate, so it would **overflow the field and corrupt the demo executable**. `projects/` is
     out of the tool's scope, and a test fails if any padded literal is longer than its width.
  4. "The decomp.wtf website" in `install.sh` means upstream's *domain*, not this product. Protected.
- **Git identity.** The app signed commits it makes (when git has no identity) as `decomp.wtf <noreply@decomp.wtf>`: an address at a domain this fork does
  not own, written into history people may publish. Now `Function_2_C_Decompiler <noreply@function-2-c-decompiler.invalid>` (`.invalid` can never
  resolve, RFC 2606), defined once in the package (`PRODUCT`, `NOREPLY_EMAIL`) and used by all three places. A real commit in a repo with no git identity
  shows it.
- The wordmark was split across markup (`decomp<b>.wtf</b>`, in two places), which no text search finds; it is now `Function_2_C_<b>Decompiler</b>`.
  **Layout: not viewed in a browser** (none was available). The name is 23 characters where it was 10 and the sidebar is 248 px, so `.brand` now
  has smaller type (13 px), `min-width: 0` and `overflow-wrap`; please look at the sidebar once. Still showing the old name: the README's banner
  images (they are pictures) and the demo ROMs' embedded credit.
- Verified on the real app: it prints `Function_2_C_Decompiler 0.10.34 on http://127.0.0.1:...`, serves a page whose title, both wordmarks and labels
  carry the new name with no old name left (apart from the credit links), and `/health` still answers `"app": "decomp-wtf"`.
- Tests: 29 in `maintenance/tests/test_maint_naming.py` (the product name, **eighteen identifiers that must not change**, the author's notice, credit
  links, the git identity, the wordmark, the demo-ROM field widths, and that re-running the tool changes nothing). One upstream test asserted the exact
  text of a message that contains the name (`test_toolchains`), so its expected string moved with the message; seven of my own tests did the same.
  **Whole suite with every tool: 481 passed and the changelog test this entry satisfies, 52 skipped, 0 failed**; test by test, nothing that passed in
  upstream's baseline or in run G fails, nothing is gone, and the 29 new tests pass.
- Not covered by the tool, on purpose: `maintenance/` (history and documentation about upstream, so the changelog keeps calling upstream's product by
  the name it had), the PowerShell installers (frozen), `tests/`.
- Nothing for users to do: the command is still `decomp`, and nothing on disk was renamed.

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
