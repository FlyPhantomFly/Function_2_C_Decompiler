# decomp.wtf's dev branch, for testing what isn't released yet (Windows, PowerShell):
#
#   irm https://decomp.wtf/dev.ps1 | iex
#
# Runs the dev branch's own installer (install.ps1 on GitHub) with DECOMP_BRANCH=dev: decomp.wtf installs from the
# branch's newest commit, and the app then offers every new commit pushed there as an update (one click).
# Back to releases: irm https://decomp.wtf/install.ps1 | iex
& {
# This fork has no Windows installer yet. This script is upstream's: it downloads decomp.wtf's own scripts and release from
# the decomp.wtf website and runs them (as root, inside WSL), and that is upstream's code, not this fork's. So it refuses,
# before it does anything. (maintenance/tests/test_maint_installers.py keeps it that way.)
throw "This Windows installer is upstream's: it downloads and runs code from decomp.wtf, not from this fork, so it is switched off. Windows isn't supported by this fork yet. Use WSL 2 and, in a Linux shell there, clone https://github.com/FlyPhantomFly/Function_2_C_Decompiler and run: bash site/public/install.sh"
$branch = if ($env:DECOMP_BRANCH) { $env:DECOMP_BRANCH } else { "dev" }
$had = $env:DECOMP_BRANCH
$env:DECOMP_BRANCH = $branch
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $script = Invoke-RestMethod -UseBasicParsing -UserAgent "decomp.wtf-installer (PowerShell)" "https://raw.githubusercontent.com/i12bp8/decomp.wtf/$branch/site/public/install.ps1"
    Invoke-Expression $script
} finally {
    $env:DECOMP_BRANCH = $had
}
}
