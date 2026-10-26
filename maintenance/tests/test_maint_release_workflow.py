"""The release workflow is the one place in CI allowed to write, so it is held to a much tighter standard than the rest.

It publishes a GitHub release (a wheel, a source distribution and their checksums) when a tag is pushed. A workflow that can write is a way into a repository
if it can be made to run someone else's code, so: it only triggers on a pushed tag (which only people with write access can make); the job that runs code
(`build`) has a read-only token; the job that can write (`publish`) runs no code from the repository, only downloads what `build` made and calls `gh release create`;
and the steps that make a release trustworthy (the tag matches the code, the tests pass, the wheel is complete, the checksums verify) are all there.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


def load() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads the key `on` as the boolean True
    return data


def run_text(job: dict) -> str:
    return "\n".join(str(s.get("run", "")) for s in job["steps"])


def test_it_runs_only_when_a_version_tag_is_pushed():
    assert load()["on"] == {"push": {"tags": ["v*"]}}


def test_the_default_token_is_read_only_and_only_the_publish_job_can_write():
    data = load()
    assert data["permissions"] == {"contents": "read"}
    assert data["jobs"]["build"].get("permissions") is None  # inherits read-only
    assert data["jobs"]["publish"]["permissions"] == {"contents": "write"}
    assert set(data["jobs"]) == {"build", "publish"}
    assert WORKFLOW.read_text(encoding="utf-8").count("contents: write") == 1


def test_the_job_that_can_write_runs_no_code_from_the_repository():
    publish = load()["jobs"]["publish"]
    assert publish["needs"] == "build"
    uses = [str(s["uses"]).split("@")[0] for s in publish["steps"] if "uses" in s]
    assert uses == ["actions/download-artifact"]  # no checkout, no uv, no pip
    commands = [line.strip() for line in run_text(publish).replace("\\\n", " ").splitlines() if line.strip()]
    assert len(commands) == 1 and commands[0].startswith("gh release create ")
    assert "--verify-tag" in commands[0] and "SHA256SUMS" in commands[0]
    assert '--title "$(cat release/title.txt)"' in commands[0]  # read from a file the build job wrote: this job computes nothing from the repository
    assert "release/*.whl release/*.tar.gz release/SHA256SUMS" in commands[0] and "title.txt" not in commands[0].split("--title")[0]  # and the title file is not a download


def test_the_build_job_does_not_keep_credentials_and_uses_nothing_unpinned():
    steps = load()["jobs"]["build"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["persist-credentials"] is False
    for s in steps:
        if "uses" in s:
            assert re.match(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$", s["uses"]), s["uses"]


def test_a_release_cannot_go_out_unless_the_tag_the_tests_the_wheel_and_the_checksums_all_check_out():
    text = run_text(load()["jobs"]["build"])
    for needed in ("bump_version.py --check", '"v$version" != "$GITHUB_REF_NAME"', "release_notes.py", "uv sync --locked", "pytest",
                   "uv build", "check_wheel.py dist/*.whl", 'pip" install', "decomp\" --help", "sha256sum --check SHA256SUMS", "SHA256SUMS"):
        assert needed in text, f"the release build no longer does: {needed}"


def test_the_notes_come_from_the_changelog_and_a_missing_entry_stops_the_release():
    text = run_text(load()["jobs"]["build"])
    # `release_notes.py` exits 2 when there is no entry, and the step is not `|| true`: the shell stops the job
    assert "release_notes.py \"$version\" > release-notes.md" in text and "|| true" not in text
    assert 'release_notes.py "$version" --title > release-title.txt' in text and "cp release-title.txt release/title.txt" in text  # the title is made here, from the changelog


def test_the_wheel_is_installed_and_run_from_outside_the_checkout():
    text = run_text(load()["jobs"]["build"])
    assert text.index('cd "$RUNNER_TEMP"') < text.index('decomp" --help')  # otherwise the checkout's own package could be imported instead of the wheel's


def test_nothing_in_it_uses_secrets_or_pushes():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text and not re.search(r"git\s+push", text)
    assert "github.token" in text  # the per-run token, scoped by the permissions above
