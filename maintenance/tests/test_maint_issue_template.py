"""The issue template must match what the app actually puts on the clipboard.

The GUI has one bug-report flow: when an import fails it shows a button, "Copy for a bug report", and copies a text whose lines are `Importing:`, `Error:`
and a fenced `Log:`. The template tells people to press that button and paste the result. If the button is renamed, or the report changes, or the template
changes its mind, people are sent to a button that is not there. These tests read the app's own files and hold the two in step in both directions.

One trap: the report contains its own fenced code block, so the template's field must not set `render:`. GitHub would wrap the paste in a second fence and
break the first.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import decompnet

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"
STATIC = ROOT / "src" / "decompnet" / "app" / "static"
FIELD_TYPES = {"markdown", "textarea", "input", "dropdown", "checkboxes"}


def form() -> dict:
    return yaml.safe_load((TEMPLATES / "bug_report.yml").read_text(encoding="utf-8"))


def field(form_: dict, id_: str) -> dict:
    return next(b for b in form_["body"] if b.get("id") == id_)


def button_label() -> str:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return re.search(r'<button[^>]*id="errCopy"[^>]*>([^<]+)</button>', html).group(1).strip()


def app_report_source() -> str:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    start = js.index("const report = [")
    return js[start: js.index("].join", start)]


# ---- it is a valid issue form ---------------------------------------------------------------------------------------------------------------------------


def test_it_is_a_valid_github_issue_form():
    f = form()
    assert {"name", "description", "body"} <= set(f) and isinstance(f["body"], list) and f["body"]
    ids = []
    for b in f["body"]:
        assert b["type"] in FIELD_TYPES, b
        if b["type"] != "markdown":
            ids.append(b["id"])
            assert re.fullmatch(r"[A-Za-z0-9_-]+", b["id"]) and b["attributes"]["label"].strip()
        if b["type"] == "dropdown":
            options = b["attributes"]["options"]
            assert options and len(set(options)) == len(options) and all(isinstance(o, str) and o.strip() for o in options)
        if b["type"] == "checkboxes":
            assert all(o["label"].strip() for o in b["attributes"]["options"])
    assert len(set(ids)) == len(ids)  # ids are unique


# ---- it matches the app -----------------------------------------------------------------------------------------------------------------------------------


def test_it_names_the_button_exactly_as_the_app_does():
    label = button_label()
    assert label == "Copy for a bug report"
    text = yaml.dump(form())
    assert label in text
    assert f"**{label}**" in field(form(), "report")["attributes"]["description"]


def test_it_points_to_the_same_fallback_the_app_does_when_the_clipboard_is_unavailable():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "select the text under What happened" in js
    assert "What happened" in field(form(), "report")["attributes"]["description"]
    assert "<summary>What happened</summary>" in (STATIC / "index.html").read_text(encoding="utf-8")


def test_the_placeholder_has_the_same_lines_the_report_has_and_nothing_the_report_does_not():
    source = app_report_source()
    placeholder = field(form(), "report")["attributes"]["placeholder"]
    for marker in ("Importing:", "Error:", "Log:"):
        assert marker in source, f"the app no longer writes {marker} in its report"
        assert marker in placeholder, f"the template does not show {marker}"
    assert placeholder.splitlines()[0].startswith(decompnet.PRODUCT)  # the report's first line starts with the product name
    assert "Function_2_C_Decompiler ${st.version" in source


def test_the_report_field_does_not_set_render_because_the_report_has_its_own_code_fence():
    attrs = field(form(), "report")["attributes"]
    assert "render" not in attrs
    assert "```" in (STATIC / "app.js").read_text(encoding="utf-8")[(STATIC / "app.js").read_text(encoding="utf-8").index("const report = ["):][:600]


def test_the_report_is_required_and_the_game_kinds_match_the_platforms_the_readme_lists():
    assert field(form(), "report")["validations"]["required"] is True
    options = " | ".join(field(form(), "kind")["attributes"]["options"])
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    table = readme[readme.index("## Platforms"):]
    for row in re.findall(r"^\| \*\*([^*|]+)\*\* \| (?!coming)", table, re.M):
        assert any(word in options for word in re.split(r"\s*·\s*", row)[:1]), f"the README lists {row!r} and the template has no matching option"


# ---- the responsible-use constraint --------------------------------------------------------------------------------------------------------------------


def test_nobody_can_submit_without_confirming_they_attached_no_game_and_no_secrets():
    boxes = field(form(), "before-you-submit")["attributes"]["options"]
    assert len(boxes) == 2 and all(b["required"] is True for b in boxes)
    assert any("game file" in b["label"] and "commercial" in b["label"] for b in boxes)
    assert any("API keys" in b["label"] for b in boxes)
    intro = form()["body"][0]
    assert intro["type"] == "markdown" and "do not attach or paste a game" in intro["attributes"]["value"]


# ---- the config -----------------------------------------------------------------------------------------------------------------------------------------------


def test_the_config_sends_security_reports_to_a_private_page_of_this_repository():
    config = yaml.safe_load((TEMPLATES / "config.yml").read_text(encoding="utf-8"))
    assert isinstance(config["blank_issues_enabled"], bool)
    (link,) = config["contact_links"]
    assert link["url"] == f"{decompnet.HOME_URL}/security/advisories/new"
    assert "private vulnerability reporting" in link["about"]  # says it must be switched on: the link is a 404 until then


def test_the_templates_use_the_product_name_and_never_the_original_projects():
    for path in TEMPLATES.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "decomp.wtf" not in text, path.name
