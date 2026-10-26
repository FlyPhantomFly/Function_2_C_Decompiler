"""The installers must install this fork's code or nothing; never upstream's.

Upstream's `install.sh` fetched its wheel from decomp.wtf (and a fallback tag from upstream's GitHub) whenever it was
piped from curl, `--source branch:` installed upstream's branch, and `dev.sh`/`dev.ps1` piped upstream's installer into a
shell. `install.ps1` ran scripts from decomp.wtf as root inside WSL. These tests run the real shell scripts with
stand-ins for `curl`, `uv` and `decomp` that record every call, so what they would fetch and install is what is asserted.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from decompnet import __version__

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "site" / "public"
FORK = "FlyPhantomFly/Function_2_C_Decompiler"
SHA = "a" * 40

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or platform.machine() not in ("x86_64", "AMD64") or shutil.which("bash") is None,
    reason="install.sh only runs on x86-64 Linux, and these tests drive it with bash",
)

CURL = """#!/bin/sh
echo "curl $*" >> "$STUB_LOG"
case "$*" in
  *api.github.com/repos/*/commits/*) printf '{"sha": "%s"}\\n' "$STUB_SHA" ;;
  *raw.githubusercontent.com*) echo 'echo "dev-installer-ran branch=$DECOMP_BRANCH"' ;;
esac
exit 0
"""
UV = """#!/bin/sh
echo "uv $*" >> "$STUB_LOG"
[ "$1" = "--version" ] && echo "uv 0.0.0"
[ "$1 $2" = "tool dir" ] && echo "$STUB_BIN"
if [ "$1 $2" = "tool install" ]; then
  for last; do :; done
  [ -d "$last" ] && echo "installed-from-dir $(grep -m1 '^version =' "$last/pyproject.toml")" >> "$STUB_LOG"
fi
exit 0
"""
DECOMP = """#!/bin/sh
echo "decomp $*" >> "$STUB_LOG"
exit 0
"""


def _executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def stubs(tmp_path):
    bindir, decomp_bin, home = tmp_path / "bin", tmp_path / "decomp-bin", tmp_path / "home"
    for d in (bindir, decomp_bin, home):
        d.mkdir()
    _executable(bindir / "curl", CURL)
    _executable(bindir / "uv", UV)
    _executable(decomp_bin / "decomp", DECOMP)
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(home), "TERM": "dumb", "STUB_LOG": str(log),
           "STUB_BIN": str(decomp_bin), "STUB_SHA": SHA}

    def run(args: list[str], *, piped: bool = False, extra_env: dict | None = None):
        script = PUBLIC / args[0]
        e = {**env, **(extra_env or {})}
        if piped:  # what `curl ... | bash` does: the script arrives on stdin, so it is not a file in a checkout
            done = subprocess.run(["bash", "-s", "--", *args[1:]], input=script.read_text(encoding="utf-8"), env=e,
                                  capture_output=True, text=True, timeout=60, start_new_session=True)
        else:
            done = subprocess.run(["bash", str(script), *args[1:]], env=e, capture_output=True, text=True, timeout=60,
                                  stdin=subprocess.DEVNULL, start_new_session=True)
        return done, log.read_text(encoding="utf-8")

    return run


def _code_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


@pytest.mark.parametrize("name", ["install.sh", "dev.sh"])
def test_the_shell_installers_parse(name):
    assert subprocess.run(["bash", "-n", str(PUBLIC / name)], capture_output=True).returncode == 0


@pytest.mark.parametrize("name", ["install.sh", "dev.sh"])
def test_no_line_of_code_in_the_shell_installers_names_upstreams_site_or_repository(name):
    for line in _code_lines(PUBLIC / name):
        assert "i12bp8" not in line and "https://decomp.wtf" not in line, f"{name}: {line.strip()}"


def installer_version() -> str:
    return re.search(r'^VERSION="([^"]+)"$', (PUBLIC / "install.sh").read_text(encoding="utf-8"), re.M).group(1)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


@pytest.mark.parametrize("args", [["install.sh", "--no-start"], ["install.sh", "--no-start", "--source", "release"]])
def test_piped_from_curl_it_installs_the_published_release_from_this_forks_tag_and_nothing_from_anywhere_else(stubs, args):
    """Until the first release was published this refused ("this fork has no published release yet"). Now `curl ... | bash` installs the tag VERSION names, the same archive the updater uses."""
    done, calls = stubs(args, piped=True)
    assert done.returncode == 0, done.stderr
    tag = f"v{installer_version()}"
    assert f"uv tool install --force --quiet --python 3.12 decompnet @ https://github.com/{FORK}/archive/refs/tags/{tag}.tar.gz" in calls
    assert "decomp install-info --channel release" in calls and f"--repo {FORK}" in calls  # its updates follow the published releases
    assert f"the published release ({tag})" in done.stdout
    assert "curl" not in calls and "decomp.wtf" not in calls and "i12bp8" not in calls


def test_the_installer_advertises_only_a_published_release_never_upstreams_old_one_or_one_the_code_has_not_reached():
    """VERSION in install.sh is read from main by the installer and by every installed app's updater. It stayed at upstream's 0.10.6 while this fork had no release, so no app could ever be told about
    one. It is moved by maintenance/tools/set_install_version.py after a release is published, and these are the rules that must hold whatever moves it."""
    v = installer_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v)
    assert version_key(v) >= (0, 11, 0), "upstream's 0.10.6 must not come back: this fork's first published release is 0.11.0"
    assert version_key(v) <= version_key(__version__), "the installer must not advertise a version the code has not reached"
    assert re.search(rf"^## \[{re.escape(v)}\] - ", (ROOT / "maintenance" / "CHANGELOG.md").read_text(encoding="utf-8"), re.M), "the release notes for it come from the changelog"


def test_a_wheel_the_user_names_themselves_is_still_allowed(stubs):
    done, calls = stubs(["install.sh", "--no-start"], piped=True, extra_env={"DECOMP_WHEEL": "https://example.test/decompnet.whl"})
    assert done.returncode == 0, done.stderr
    assert "uv tool install --force --quiet --python 3.12 decompnet @ https://example.test/decompnet.whl" in calls
    assert "decomp.wtf" not in calls and "i12bp8" not in calls


def test_a_branch_install_resolves_and_installs_from_this_forks_github_only(stubs):
    done, calls = stubs(["install.sh", "--no-start", "--source", "branch:main"], piped=True)
    assert done.returncode == 0, done.stderr
    assert f"curl -fsSL -H Accept: application/vnd.github+json https://api.github.com/repos/{FORK}/commits/main" in calls
    assert f"decompnet @ https://github.com/{FORK}/archive/{SHA}.tar.gz" in calls
    assert "decomp.wtf" not in calls and "i12bp8" not in calls


def test_run_from_a_checkout_it_installs_that_checkouts_source_and_fetches_no_code(stubs):
    done, calls = stubs(["install.sh", "--no-start"])
    assert done.returncode == 0, done.stderr
    assert f'installed-from-dir version = "{__version__}"' in calls
    assert "curl" not in calls  # nothing downloaded to install it
    assert "decomp.wtf" not in calls and "i12bp8" not in calls
    assert "decomp setup" in calls and "decomp install-info" in calls


def test_the_dev_script_runs_this_forks_installer_not_upstreams(stubs):
    done, calls = stubs(["dev.sh"], piped=True)
    assert done.returncode == 0, done.stderr
    assert f"https://raw.githubusercontent.com/{FORK}/main/site/public/install.sh" in calls
    assert "i12bp8" not in calls and "decomp.wtf" not in calls
    assert "dev-installer-ran branch=main" in done.stdout


@pytest.mark.parametrize("name", ["install.ps1", "dev.ps1"])
def test_the_powershell_installers_refuse_before_they_download_anything(name):
    text = (PUBLIC / name).read_text(encoding="utf-8")
    refuse = text.index("throw ")
    for fetch in ("Invoke-RestMethod", "Invoke-WebRequest", "Invoke-Expression", "irm "):
        for line in _code_lines(PUBLIC / name):
            if fetch in line:
                assert text.index(line) > refuse, f"{name}: {fetch} comes before the refusal"
    assert "upstream" in text[refuse:refuse + 700].lower()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="needs PowerShell (pwsh)")
@pytest.mark.parametrize("name", ["install.ps1", "dev.ps1"])
def test_the_powershell_installers_really_stop_when_run(name):
    done = subprocess.run(["pwsh", "-NoProfile", "-File", str(PUBLIC / name)], capture_output=True, text=True, timeout=60)
    assert done.returncode != 0 and "upstream" in (done.stderr + done.stdout).lower()


def test_the_docker_route_installs_from_this_forks_branch_not_a_release():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    source = compose["services"]["decomp"]["environment"]["DECOMP_SOURCE"]
    assert source.startswith("branch:") and source != "release"
