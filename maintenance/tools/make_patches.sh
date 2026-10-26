#!/usr/bin/env bash
# Regenerate maintenance/patches: one `git am` patch per commit since BASE (default: the tag upstream-0.10.6).
#
#   maintenance/tools/make_patches.sh [BASE]
#
# The patches leave out maintenance/patches itself (they would otherwise contain each other), and `--zero-commit` blanks
# the commit ids, so the output is the same whatever happens to the commits afterwards (an amend, a rebase).
set -euo pipefail
cd "$(dirname "$0")/../.."
BASE="${1:-upstream-0.10.6}"
OUT=maintenance/patches
git rev-parse --verify --quiet "$BASE^{commit}" >/dev/null || { echo "no such commit: $BASE" >&2; exit 1; }
rm -f "$OUT"/0*.patch
git format-patch --zero-commit --no-signature --quiet -o "$OUT" "$BASE..HEAD" -- . ":(exclude)$OUT"
echo "$(ls "$OUT"/0*.patch | wc -l) patches in $OUT"
