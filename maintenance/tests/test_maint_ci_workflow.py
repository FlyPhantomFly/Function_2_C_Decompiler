"""The CI workflow must not become a way into this repository.

A third-party action referenced by a movable tag (`@v4`) can change under us; a workflow with write access or one
triggered by `pull_request_target` can be turned against the repository by a pull request. These checks keep the
workflow to: actions pinned to a full commit SHA, read-only token, no `pull_request_target`, no secrets.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
SHA_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}(\s+#.*)?$")


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["on"] = data.pop(True, data.get("on"))  # YAML 1.1 reads the key `on` as the boolean True
    return data


def _files() -> list[Path]:
    found = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert found, "no workflow files in .github/workflows"
    return found


def test_every_third_party_action_is_pinned_to_a_full_commit_sha():
    for path in _files():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:-\s*)?uses:\s*(\S.*?)\s*$", line)
            if m and not m.group(1).startswith("./"):
                assert SHA_PINNED.match(m.group(1)), f"{path.name}: not pinned to a commit: {line.strip()}"


def test_the_token_is_read_only_by_default():
    for path in _files():
        assert _load(path).get("permissions") == {"contents": "read"}, path.name


def test_no_workflow_runs_untrusted_code_with_a_privileged_trigger():
    for path in _files():
        triggers = _load(path)["on"]
        names = set(triggers) if isinstance(triggers, dict) else set([triggers] if isinstance(triggers, str) else triggers)
        assert "pull_request_target" not in names, path.name
        assert "workflow_run" not in names, path.name


def test_no_workflow_uses_secrets_or_writes_to_the_repository():
    for path in _files():
        text = path.read_text(encoding="utf-8")
        assert "secrets." not in text, path.name
        assert "contents: write" not in text, path.name
        assert not re.search(r"git\s+push", text), path.name


def test_checkout_does_not_leave_the_token_in_the_workspace():
    for path in _files():
        data = _load(path)
        for job in data["jobs"].values():
            for step in job["steps"]:
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step.get("with", {}).get("persist-credentials") is False, f"{path.name}: {job}"


def test_the_workflow_runs_the_checks_this_fork_relies_on():
    text = "\n".join(p.read_text(encoding="utf-8") for p in _files())
    for needed in ("uv sync --locked", "uv lock --check", "bump_version.py --check", "compileall", "E9,F63,F7,F82", "pytest"):
        assert needed in text, f"CI no longer runs: {needed}"
