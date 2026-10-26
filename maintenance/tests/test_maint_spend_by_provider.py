"""The budget knows which provider spent what.

Before: two running totals per project, and an API agent's dollars existed only when the provider happened to report them (OpenRouter does; OpenAI and DeepSeek
do not). Now: each endpoint can carry prices (input, output, and an optional cached-input rate, because OpenAI and DeepSeek both discount cached tokens and
report them), a request's cost is the provider's own figure when it gives one and the computed one otherwise, and every charge is logged with the provider, the
agent and the model that incurred it. The global cap still counts everything together; the breakdown shows OpenAI against DeepSeek, today or later, because the tags
are stored and not only summed.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from decompnet.app import agents
from decompnet.app.engine import RomNetwork
from decompnet.app.server import Settings, _session_options
from decompnet.store import SCHEMA_VERSION, Store

FIXTURE = Path(__file__).parent / "fixtures" / "db-0.10.6.sqlite"
OPENAI_PRICES = {"price_in": 2.5, "price_out": 10.0, "price_cached": 1.25}  # USD per million tokens: arbitrary test numbers, not a real price list
DEEPSEEK_PRICES = {"price_in": 0.27, "price_out": 1.10, "price_cached": 0.07}


REAL_CLIENT = httpx.Client  # taken once, at import: patching it twice in one test would wrap the first patch


class FakeStop:
    def wait(self, seconds):
        return False

    def is_set(self):
        return False


# ---- the schema --------------------------------------------------------------------------------------------------------------------------------


def test_schema_2_adds_the_spend_log_and_a_v1_database_is_migrated_with_a_copy_kept(tmp_path):
    assert SCHEMA_VERSION >= 2
    path = tmp_path / "d.db"
    Store(path).conn.close()
    con = sqlite3.connect(path)
    assert {r[1] for r in con.execute("PRAGMA table_info(spend_log)")} == {"id", "project_id", "at", "provider", "agent", "model", "usd", "tokens"}
    con.execute("DROP TABLE spend_log")
    con.execute("PRAGMA user_version = 1")  # what a database from before this version looks like
    con.commit()
    con.close()
    Store(path).conn.close()
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert con.execute("SELECT COUNT(*) FROM spend_log").fetchone()[0] == 0
    assert (tmp_path / "d.db.bak-v1").exists()


def test_the_upstream_0_10_6_database_still_opens_and_gets_the_new_table(tmp_path):
    path = tmp_path / "up.db"
    shutil.copy(FIXTURE, path)
    Store(path).conn.close()
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM spend_log").fetchone()[0] == 0 and con.execute("SELECT COUNT(*) FROM functions").fetchone()[0] == 13


# ---- what a request costs ------------------------------------------------------------------------------------------------------------------------


def test_the_cost_is_computed_from_prices_with_cached_input_at_its_own_rate_openai_style():
    usage = {"prompt_tokens": 10_000, "completion_tokens": 2_000, "prompt_tokens_details": {"cached_tokens": 6_000}}
    # 4,000 uncached in at 2.5, 6,000 cached at 1.25, 2,000 out at 10  (per million)
    assert agents.computed_cost(usage, OPENAI_PRICES) == pytest.approx(4_000 * 2.5 / 1e6 + 6_000 * 1.25 / 1e6 + 2_000 * 10 / 1e6)


def test_the_cost_is_computed_deepseek_style_from_the_cache_hit_count():
    usage = {"prompt_tokens": 10_000, "completion_tokens": 1_000, "prompt_cache_hit_tokens": 9_000, "prompt_cache_miss_tokens": 1_000}
    assert agents.computed_cost(usage, DEEPSEEK_PRICES) == pytest.approx(1_000 * 0.27 / 1e6 + 9_000 * 0.07 / 1e6 + 1_000 * 1.10 / 1e6)


def test_without_a_cached_rate_cached_tokens_cost_the_normal_input_rate():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0, "prompt_cache_hit_tokens": 400_000}
    assert agents.computed_cost(usage, {"price_in": 2.0, "price_out": 8.0}) == pytest.approx(2.0)


@pytest.mark.parametrize("prices", [{}, {"price_in": 2.5}, {"price_out": 10.0}, {"price_in": 0, "price_out": 0}, {"price_in": -1, "price_out": 5},
                                    {"price_in": "free", "price_out": 5}, {"price_in": float("nan"), "price_out": 5}, {"price_in": True, "price_out": 5}])
def test_nothing_is_computed_unless_both_prices_are_real_positive_numbers(prices):
    assert agents.computed_cost({"prompt_tokens": 5_000, "completion_tokens": 5_000}, prices) == 0.0


@pytest.mark.parametrize("usage", [{}, {"prompt_tokens": "lots", "completion_tokens": 10}, {"prompt_tokens": -5, "completion_tokens": 10}, {"prompt_tokens": True, "completion_tokens": 1}])
def test_unusable_token_counts_never_produce_a_negative_or_invented_cost(usage):
    cost = agents.computed_cost(usage, OPENAI_PRICES)
    assert cost >= 0 and cost == cost  # not negative, not NaN


def test_cached_tokens_cannot_exceed_the_prompt_and_make_a_negative_uncached_count():
    usage = {"prompt_tokens": 100, "completion_tokens": 0, "prompt_cache_hit_tokens": 5_000}
    assert agents.computed_cost(usage, OPENAI_PRICES) == pytest.approx(100 * 1.25 / 1e6)


def test_what_the_provider_reports_wins_over_a_computed_cost():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 0, "cost": 0.5}
    assert agents.request_cost(usage, OPENAI_PRICES) == 0.5
    assert agents.request_cost({"prompt_tokens": 1_000_000, "completion_tokens": 0}, OPENAI_PRICES) == pytest.approx(2.5)
    assert agents.request_cost({"prompt_tokens": 10, "completion_tokens": 10}, {}) == 0.0


# ---- the log and the subtotals -------------------------------------------------------------------------------------------------------------------------


@pytest.fixture
def net(tmp_path):
    network = RomNetwork(tmp_path / "t.db", tmp_path)
    network.store.conn.execute("INSERT INTO projects(slug, root, config) VALUES ('game', '/x', '{}')")
    return network


def test_a_charge_updates_the_totals_and_writes_one_tagged_row_together(net):
    net.add_spend("game", 0.25, 1_000, provider="openai", agent="api-1", model="gpt-x")
    assert net.spend("game") == {"usd": 0.25, "tokens": 1_000}
    row = net.store.one("SELECT provider, agent, model, usd, tokens FROM spend_log")
    assert (row["provider"], row["agent"], row["model"], row["usd"], row["tokens"]) == ("openai", "api-1", "gpt-x", 0.25, 1_000)


def test_the_old_call_without_tags_still_works_and_counts_as_untagged(net):
    net.add_spend("game", 0.25, 0)  # exactly as upstream's test calls it
    net.add_spend("game", 0.5, 1_200, provider="deepseek", agent="api-2", model="m")
    breakdown = net.spend_breakdown("game")
    assert breakdown["total"] == {"usd": 0.75, "tokens": 1_200}
    assert [p["provider"] for p in breakdown["providers"]] == ["deepseek"]
    assert breakdown["untagged"] == {"usd": 0.25, "tokens": 0}  # spent before providers were tagged: shown, not hidden


def test_nothing_is_logged_for_a_charge_of_nothing(net):
    net.add_spend("game", 0.0, 0, provider="openai", agent="a")
    assert net.store.one("SELECT COUNT(*) AS n FROM spend_log")["n"] == 0 and net.spend("game") is None


def test_the_breakdown_gives_a_subtotal_per_provider_and_per_agent_within_it_largest_first(net):
    for provider, agent, usd in (("openai", "api-1", 1.0), ("openai", "api-2", 0.5), ("deepseek", "api-3", 0.2), ("openai", "api-1", 0.25), ("deepseek", "api-3", 0.05)):
        net.add_spend("game", usd, 100, provider=provider, agent=agent, model="m")
    b = net.spend_breakdown("game")
    assert [(p["provider"], p["usd"], p["requests"]) for p in b["providers"]] == [("openai", 1.75, 3), ("deepseek", 0.25, 2)]
    assert [(a["agent"], a["usd"]) for a in b["providers"][0]["agents"]] == [("api-1", 1.25), ("api-2", 0.5)] or sorted((a["agent"], a["usd"]) for a in b["providers"][0]["agents"]) == [("api-1", 1.25), ("api-2", 0.5)]
    assert b["total"]["usd"] == 2.0 and b["untagged"] is None


def test_the_one_global_cap_counts_every_provider_together(net):
    manager = agents.Manager.__new__(agents.Manager)
    manager.net, manager.budget = net, lambda: 1.0
    net.add_spend("game", 0.6, 1, provider="openai", agent="a")
    assert manager.over_budget("game") is None  # neither provider is over, and the sum is not yet
    net.add_spend("game", 0.5, 1, provider="deepseek", agent="b")
    assert manager.over_budget("game") == 1.0  # 0.6 + 0.5 crosses the cap although each is under it


def test_a_provider_tag_is_normalised_and_bounded(net):
    net.add_spend("game", 1.0, 1, provider="  OpenAI  ", agent="a" * 500, model="m" * 500)
    row = net.store.one("SELECT provider, agent, model FROM spend_log")
    assert row["provider"] == "openai" and len(row["agent"]) <= 120 and len(row["model"]) <= 120


# ---- prices on an endpoint ----------------------------------------------------------------------------------------------------------------------------


def test_prices_are_saved_with_the_endpoint_returned_to_the_gui_and_passed_to_its_sessions(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    saved = settings.save_endpoint({"provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-x", "api_key": "sk-secret-1234",
                                    "price_in": "2.5", "price_out": "10", "price_cached": "1.25"})
    assert (saved["price_in"], saved["price_out"], saved["price_cached"]) == (2.5, 10.0, 1.25)
    assert _session_options(saved)["price_in"] == 2.5 and _session_options(saved)["price_cached"] == 1.25
    public = settings.public()["endpoints"][0]
    assert public["price_out"] == 10.0 and "sk-secret-1234" not in json.dumps(public)


def test_a_price_can_be_cleared_and_a_bad_one_is_refused_with_a_sentence(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    e = settings.save_endpoint({"provider": "deepseek", "price_in": 0.27, "price_out": 1.1})
    cleared = settings.save_endpoint({"id": e["id"], "price_in": "", "price_out": ""})
    assert "price_in" not in cleared and "price_out" not in cleared
    for bad in ("cheap", "-3", "nan", "inf"):
        with pytest.raises(ValueError, match="US dollars per million tokens"):
            settings.save_endpoint({"id": e["id"], "price_in": bad})
    assert settings.endpoint(e["id"]).get("price_in") is None  # the failed saves changed nothing


def test_an_endpoint_without_prices_carries_none_into_its_session():
    options = _session_options(agents.endpoint_entry({"provider": "ollama", "id": "e1"}))
    assert not any(k.startswith("price_") for k in options)


# ---- through the real agent loop ------------------------------------------------------------------------------------------------------------------------


def run_session(monkeypatch, net, replies, options, agent_name):
    manager = agents.Manager.__new__(agents.Manager)
    manager.net = SimpleNamespace(fork_slug=lambda slug: None, add_spend=net.add_spend, spend=net.spend)
    manager.prompt = lambda s: "go"
    manager.budget = lambda: 0.0
    script = list(replies)
    monkeypatch.setattr(agents.httpx, "Client", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=json.dumps(script.pop(0) if len(script) > 1 else script[0]).encode(), headers={"content-type": "application/json"})), **kw))
    s = agents.Session(agent_name, "api", "T", "game", agent_name, {"base_url": "http://8.8.8.8/v1", "max_steps": 1, **options})
    s.stop = FakeStop()
    manager._run_api(s, SimpleNamespace(id=1))
    return s


def test_two_priced_endpoints_spend_into_their_own_subtotals_and_the_total_is_their_sum(monkeypatch, net):
    openai = {"choices": [{"message": {"role": "assistant", "content": "done"}}],
              "usage": {"prompt_tokens": 100_000, "completion_tokens": 10_000, "total_tokens": 110_000, "prompt_tokens_details": {"cached_tokens": 50_000}}}
    deepseek = {"choices": [{"message": {"role": "assistant", "content": "done"}}],
                "usage": {"prompt_tokens": 100_000, "completion_tokens": 10_000, "total_tokens": 110_000, "prompt_cache_hit_tokens": 90_000}}
    run_session(monkeypatch, net, [openai], {"provider": "openai", "provider_name": "OpenAI", "model": "gpt-x", **OPENAI_PRICES}, "api-1")
    run_session(monkeypatch, net, [deepseek], {"provider": "deepseek", "provider_name": "DeepSeek", "model": "ds", **DEEPSEEK_PRICES}, "api-2")
    b = net.spend_breakdown("game")
    expect_openai = 50_000 * 2.5 / 1e6 + 50_000 * 1.25 / 1e6 + 10_000 * 10 / 1e6
    expect_deepseek = 10_000 * 0.27 / 1e6 + 90_000 * 0.07 / 1e6 + 10_000 * 1.10 / 1e6
    by = {p["provider"]: p for p in b["providers"]}
    assert by["openai"]["usd"] == pytest.approx(expect_openai, abs=1e-6) and by["deepseek"]["usd"] == pytest.approx(expect_deepseek, abs=1e-6)
    assert by["openai"]["agents"][0]["agent"] == "api-1" and by["openai"]["agents"][0]["model"] == "gpt-x"
    assert net.spend("game")["usd"] == pytest.approx(expect_openai + expect_deepseek, abs=1e-6) and b["untagged"] is None


def test_a_custom_server_is_tagged_by_its_name_not_by_the_word_custom(monkeypatch, net):
    body = {"choices": [{"message": {"role": "assistant", "content": "x"}}], "usage": {"total_tokens": 10}}
    run_session(monkeypatch, net, [body], {"provider": "custom", "provider_name": "gpu-box", "model": "m"}, "api-3")
    assert [p["provider"] for p in net.spend_breakdown("game")["providers"]] == ["gpu-box"]


def test_an_endpoint_with_no_prices_and_no_reported_cost_records_tokens_under_its_provider_and_no_dollars(monkeypatch, net):
    body = {"choices": [{"message": {"role": "assistant", "content": "x"}}], "usage": {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600}}
    run_session(monkeypatch, net, [body], {"provider": "openai", "model": "m"}, "api-4")
    (p,) = net.spend_breakdown("game")["providers"]
    assert (p["provider"], p["usd"], p["tokens"]) == ("openai", 0.0, 600)


def test_a_command_line_agents_spend_is_tagged_with_its_kind(net):
    manager = agents.Manager.__new__(agents.Manager)
    manager.net = net
    s = agents.Session("claude-1", "claude", "Claude Code #1", "game", "claude-1", {"model": "sonnet"})
    manager._account(s, {"usd": 0.4, "tokens": 900})
    (p,) = net.spend_breakdown("game")["providers"]
    assert p["provider"] == "claude" and p["usd"] == 0.4 and p["agents"][0] == {"agent": "claude-1", "model": "sonnet", "usd": 0.4, "tokens": 900, "requests": 1}


# ---- the GUI ----------------------------------------------------------------------------------------------------------------------------------------------

STATIC = Path(__file__).resolve().parents[2] / "src" / "decompnet" / "app" / "static"


def test_the_endpoint_form_has_the_three_price_fields_and_sends_them_and_the_overview_shows_subtotals():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for needle in ('data-f="pin"', 'data-f="pout"', 'data-f="pcached"', "price_in:", "price_out:", "price_cached:", "spend_by"):
        assert needle in js, needle
    assert "per million tokens" in js
