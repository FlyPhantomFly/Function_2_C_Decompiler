# maintenance/

Everything generated while taking over and maintaining this fork lives here, apart from upstream's own files.

| Path | What it is |
| --- | --- |
| `CHANGELOG.md` | One entry per version: what changed, why, how it was verified. **Start here to see what has been done.** |
| `ARCHITECTURE.md` | How the code works, with each finding marked as read or as verified by running it. |
| `MAINTENANCE_PLAN.md` | The phased plan: what to do next and why. |
| `CLAUDE.md` | Instructions for Claude Code sessions (commands, release rule, invariants, review gates). |
| `baseline/` | The Phase 0 test baseline on upstream 0.10.6: raw output, classified summaries, a script that rebuilds the test environment. |
| `tools/` | Scripts: `bump_version.py`, `summarize_junit.py`, `check_toolchains.py` (dead links and changed files in the pinned compiler downloads), `rename_product.py` (the product name, with identifiers and credits protected), `make_patches.sh`, `screenshot_ui.py` (see the GUI at two widths with a headless browser), `eval_agent.py` (measure a model on the demo ROM; `--oracle` checks the harness itself). |
| `tests/` | Tests we added (`test_maint_*.py`). Upstream's tests stay in `tests/`. |
| `patches/` | Each change as a patch against the `upstream-0.10.6` tag, for review. Derived from git history; not edited by hand. |

## Versions

Upstream's last release was 0.10.6. Each change here is the next patch number (0.10.7, 0.10.8, ...). Plain
`X.Y.Z` is deliberate: the updater's comparison reads only the first three numbers. The version is kept in three
places that must agree (`pyproject.toml`, `src/decompnet/__init__.py`, `uv.lock`); `tools/bump_version.py` moves them
together and `tests/test_maint_release_hygiene.py` fails if they drift or the changelog is missing an entry.

## What is outside this folder, and why

- `CLAUDE.md` at the repository root: one line, `@maintenance/CLAUDE.md`, so Claude Code finds the instructions.
- `.github/workflows/`: GitHub only reads workflows from there (added by the CI change).
- Edits to upstream files (for example `src/decompnet/app/updates.py`). Every such edit is listed in its changelog
  entry and reproduced in `patches/`.
- A dependency in the other direction: upstream's tests import `maintenance/testgates.py` (the shared skip
  conditions), so the folder cannot simply be deleted without editing those tests.
- `site/public/install.sh` and `install.ps1` keep `VERSION="0.10.6"`: it names a wheel that has to exist on a server.
  Do not move it until a release is actually published.
