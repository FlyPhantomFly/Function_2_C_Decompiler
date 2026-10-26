#!/usr/bin/env bash
# This fork's branch installer, for testing what isn't released yet (Linux). From a clone, `bash site/public/install.sh`
# is simpler; this runs a branch's own installer straight from this fork's GitHub repository:
#
#   curl -fsSL https://raw.githubusercontent.com/FlyPhantomFly/Function_2_C_Decompiler/main/site/public/dev.sh | bash
#   (another branch: set DECOMP_BRANCH=<name>)
#
# decomp.wtf installs from the branch's newest commit, and the app then offers every new commit pushed there as an update.
set -euo pipefail
BRANCH="${DECOMP_BRANCH:-main}"
curl -fsSL "https://raw.githubusercontent.com/FlyPhantomFly/Function_2_C_Decompiler/$BRANCH/site/public/install.sh" | DECOMP_BRANCH="$BRANCH" bash -s -- "$@"
