"""What the running app, the team-room page and the Claude Code plugin tell people (and agents) to do and visit.

Upstream's UI linked to its website and issue tracker, the team-room page sent guests to its site to get the app, and the
plugin's skill told the AI agent to run `curl https://decomp.wtf/install.sh | bash`. An agent follows such a line; this
fork's copy has to send it to this fork's code, and nowhere else.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORK = "https://github.com/FlyPhantomFly/Function_2_C_Decompiler"
UPSTREAM_REPO = "github.com/i12bp8/decomp.wtf"
STATIC = ROOT / "src" / "decompnet" / "app" / "static"
SKILL = ROOT / "plugins" / "decomp-wtf" / "skills" / "decompile" / "SKILL.md"
PLUGIN = ROOT / "plugins" / "decomp-wtf" / ".claude-plugin" / "plugin.json"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"


def _app_text() -> dict[str, str]:
    files = [p for p in STATIC.rglob("*") if p.suffix in (".js", ".html", ".css")] + [ROOT / "src" / "decompnet" / "app" / "collab.py"]
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in files}


def test_no_page_the_app_serves_links_to_upstreams_website():
    for name, text in _app_text().items():
        assert "https://decomp.wtf" not in text, name


def test_the_only_link_to_upstream_in_the_app_is_one_credit_in_settings():
    hits = {name: text.count(UPSTREAM_REPO) for name, text in _app_text().items() if UPSTREAM_REPO in text}
    assert hits == {"src/decompnet/app/static/app.js": 1}, hits
    line = next(l for l in (STATIC / "app.js").read_text(encoding="utf-8").splitlines() if UPSTREAM_REPO in l)
    assert "Original project" in line


def test_bug_report_and_source_links_go_to_this_fork():
    js, html = (STATIC / "app.js").read_text(encoding="utf-8"), (STATIC / "index.html").read_text(encoding="utf-8")
    assert f"{FORK}/issues" in js and f"{FORK}/issues/new" in html
    assert f'href="{FORK}" target="_blank" rel="noopener">Source code</a>' in js
    assert f"<a href='{FORK}'>" in (ROOT / "src" / "decompnet" / "app" / "collab.py").read_text(encoding="utf-8")


def test_the_skill_never_tells_an_agent_to_pipe_a_download_into_a_shell():
    text = SKILL.read_text(encoding="utf-8")
    assert "decomp.wtf/install" not in text and "i12bp8" not in text
    assert not re.search(r"\|\s*(ba)?sh\b|\|\s*iex\b", text), "the skill pipes a download into a shell"
    assert FORK in text and "site/public/install.sh" in text


def test_the_plugin_manifests_name_this_fork_and_agree_on_the_version():
    plugin, market = json.loads(PLUGIN.read_text(encoding="utf-8")), json.loads(MARKET.read_text(encoding="utf-8"))
    assert plugin["repository"] == plugin["homepage"] == FORK
    assert plugin["author"]["name"] == market["owner"]["name"] == "PhantomThreads"
    assert "decomp.wtf" not in json.dumps(plugin["author"]) + json.dumps(market["owner"])
    assert market["plugins"][0]["version"] == plugin["version"]
    assert market["name"] == "decomp-wtf" and plugin["name"] == "decomp-wtf"  # the documented install command names these
