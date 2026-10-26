"""The eval harness (maintenance/tools/eval_agent.py): how a model, or a prompt change, is measured on the demo ROM.

The pure parts are tested anywhere. The end-to-end runs need the KMC compiler and the sandbox and are skipped without them. The
most important test is that the harness's own self-check can FAIL: a scripted oracle model that knows two answers must score 2 of 2,
and when it is made to give a wrong one the harness must exit 1. A check that cannot fail would prove nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("eval_agent", ROOT / "maintenance" / "tools" / "eval_agent.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


e = _load()
CANNOT_RUN = e.problem()
needs_demo = pytest.mark.skipif(bool(CANNOT_RUN), reason=CANNOT_RUN or "")


def row(name, matched, **kw):
    return {"function": name, "matched": matched, "steps": kw.get("steps", 3), "tokens": kw.get("tokens", 100), "usd": kw.get("usd", 0.0),
            "seconds": kw.get("seconds", 1.0), "error": "", **({"skipped": kw["skipped"]} if "skipped" in kw else {})}


# ---- the parts that need nothing ------------------------------------------------------------------------------------------------------------------


def test_the_evaluation_order_is_smallest_first_then_by_name_and_a_missing_size_counts_as_zero():
    rows = [{"name": "f_c", "size": 8}, {"name": "f_b", "size": 8}, {"name": "f_a", "size": 100}, {"name": "f_z", "size": None}]
    assert e.order_open(rows) == ["f_z", "f_b", "f_c", "f_a"]


def test_the_oracle_claims_then_compiles_its_answer_then_says_it_is_done_and_admits_what_it_does_not_know():
    focus = {"role": "user", "content": "context..." + e.focus_text("func_800007F4")}
    first = e.oracle_reply([focus])["tool_calls"][0]["function"]
    assert first["name"] == "claim_function" and json.loads(first["arguments"]) == {"function": "func_800007F4"}
    second = e.oracle_reply([focus, {"role": "tool", "content": "claimed"}])["tool_calls"][0]["function"]
    assert second["name"] == "compile_and_diff" and json.loads(second["arguments"])["source"] == e.ABS
    assert e.oracle_reply([focus, {"role": "tool", "content": "a"}, {"role": "tool", "content": "b"}]) == {"content": "Matched."}
    unknown = {"role": "user", "content": e.focus_text("func_00000000")}
    assert e.oracle_reply([unknown]) == {"content": "I don't know this one."}


def test_the_focus_instruction_and_the_pattern_that_finds_it_agree():
    """A capital W in one and not the other made the first oracle run answer 'I don't know' to everything."""
    assert e.FOCUS.search(e.focus_text("func_80000808")).group(1) == "func_80000808"


def test_the_summary_counts_skipped_functions_apart_from_failures_and_divides_cost_by_matches():
    s = e.summarize([row("a", True, usd=0.10, tokens=1000, steps=4), row("b", False, usd=0.30, tokens=3000, steps=8),
                     row("c", False, skipped="the $0.40 cap was reached")])
    assert (s["attempted"], s["matched"], s["skipped"], s["rate"]) == (2, 1, 1, 0.5)
    assert s["usd"] == 0.4 and s["usd_per_match"] == 0.4 and s["tokens"] == 4000 and s["mean_steps"] == 6.0


def test_a_summary_of_nothing_does_not_divide_by_zero():
    assert e.summarize([])["rate"] == 0.0 and e.summarize([row("a", False)])["usd_per_match"] is None


def test_the_report_keeps_the_endpoints_host_and_never_a_key_or_credentials_in_the_address():
    report = e.build_report(model="m", base_url="https://user:hunter2@api.example.com/v1?key=sk-secret", oracle=False, max_steps=40,
                            free={"autopilot": True, "matched": 20, "functions": 95}, rows=[row("a", True)], version="0.0.0")
    text = json.dumps(report)
    assert report["endpoint"] == "api.example.com" and "hunter2" not in text and "sk-secret" not in text and "key" not in text.replace("keys", "")


def test_compare_names_the_functions_gained_and_lost_and_warns_when_the_sets_differ():
    a = e.build_report(model="before", base_url="", oracle=False, max_steps=40, free={}, rows=[row("f1", True), row("f2", False), row("f3", True)], version="v")
    b = e.build_report(model="after", base_url="", oracle=False, max_steps=40, free={}, rows=[row("f1", True), row("f2", True), row("f3", False)], version="v")
    out = e.compare(a, b)
    assert "gained    f2" in out and "lost      f3" in out and "2/3  ->  2/3  (+0)" in out and "NOTE" not in out
    c = e.build_report(model="other", base_url="", oracle=False, max_steps=40, free={}, rows=[row("f1", True), row("f9", True)], version="v")
    assert "NOTE: the function sets differ" in e.compare(a, c)


def test_the_report_says_when_the_free_baseline_was_not_measured_rather_than_showing_a_zero():
    skipped = e.build_report(model="m", base_url="", oracle=True, max_steps=1, free={"autopilot": False, "matched": 0, "functions": 95}, rows=[row("a", True)], version="v")
    assert "not measured" in e.render(skipped) and "matched 0 of 95" not in e.render(skipped)
    measured = e.build_report(model="m", base_url="", oracle=False, max_steps=1, free={"autopilot": True, "matched": 20, "functions": 95}, rows=[row("a", True)], version="v")
    assert "autopilot matched 20 of 95" in e.render(measured)


def test_a_key_is_never_taken_from_the_command_line_and_is_not_echoed_back(capsys):
    """argparse treats an unambiguous prefix as the option, so `--api-key sk-...` used to be read as `--api-key-env sk-...`: the secret became an
    environment variable name and was printed in the error. Now it is refused outright, without repeating it."""
    with pytest.raises(SystemExit) as exit_:
        e.main(["--api-key", "sk-supersecret", "--base-url", "https://x.example/v1", "--model", "m"])
    err = capsys.readouterr().err
    assert exit_.value.code == 2 and "EVAL_API_KEY" in err and "sk-supersecret" not in err


def test_a_remote_endpoint_without_a_key_in_the_environment_is_refused_but_a_local_server_needs_none(monkeypatch, capsys):
    monkeypatch.delenv("EVAL_API_KEY", raising=False)
    monkeypatch.setattr(e, "evaluate", lambda args: 0)
    with pytest.raises(SystemExit) as exit_:
        e.main(["--base-url", "https://api.example.com/v1", "--model", "m"])
    assert exit_.value.code == 2 and "EVAL_API_KEY" in capsys.readouterr().err
    assert e.main(["--base-url", "http://127.0.0.1:11434/v1", "--model", "llama"]) == 0


def test_it_says_what_it_needs_when_given_nothing(capsys):
    with pytest.raises(SystemExit):
        e.main([])
    assert "--oracle" in capsys.readouterr().err


def test_compare_runs_from_the_command_line_on_two_result_files(tmp_path, capsys):
    a = e.build_report(model="before", base_url="", oracle=False, max_steps=40, free={}, rows=[row("f1", False)], version="v")
    b = e.build_report(model="after", base_url="", oracle=False, max_steps=40, free={}, rows=[row("f1", True)], version="v")
    (tmp_path / "a.json").write_text(json.dumps(a), encoding="utf-8")
    (tmp_path / "b.json").write_text(json.dumps(b), encoding="utf-8")
    assert e.main(["--compare", str(tmp_path / "a.json"), str(tmp_path / "b.json")]) == 0
    assert "gained    f1" in capsys.readouterr().out


# ---- end to end, with the real compiler and judge --------------------------------------------------------------------------------------------------


@needs_demo
def test_the_oracle_matches_what_it_knows_through_the_real_compiler_and_the_report_is_written_without_a_key(tmp_path):
    out = tmp_path / "oracle.json"
    assert e.main(["--oracle", "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["functions"] == ["func_800007F4", "func_80000808"] and report["summary"]["matched"] == 2 and report["summary"]["rate"] == 1.0
    assert all(r["steps"] == 2 for r in report["results"]) and report["oracle"] is True and report["endpoint"] == ""
    assert "api_key" not in out.read_text(encoding="utf-8")


@needs_demo
def test_the_self_check_can_fail_a_wrong_answer_makes_the_harness_exit_1_and_for_that_reason_alone(monkeypatch, capsys, tmp_path):
    monkeypatch.setitem(e.ORACLE, "func_800007F4", "s32 func_800007F4(s32 v) { return v; }")  # compiles, does not match
    out = tmp_path / "wrong.json"
    assert e.main(["--oracle", "--out", str(out)]) == 1
    assert "the HARNESS is broken" in capsys.readouterr().err
    wrong = json.loads(out.read_text(encoding="utf-8"))["results"][0]
    # it really compiled the wrong answer and was judged not a match: not a crash, not a transport error, not a missing function
    assert wrong["function"] == "func_800007F4" and wrong["matched"] is False and wrong["steps"] == 2 and wrong["error"] == ""


@needs_demo
def test_running_the_harness_twice_in_one_process_leaves_no_patch_behind_and_gives_the_same_answer(tmp_path):
    import httpx

    before = httpx.Client
    for n in (1, 2):
        out = tmp_path / f"run{n}.json"
        assert e.main(["--oracle", "--out", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8"))["summary"]["matched"] == 2
        assert httpx.Client is before  # the scripted model was in place for the run only


@needs_demo
def test_a_function_the_oracle_does_not_know_is_a_miss_not_a_harness_failure(tmp_path):
    out = tmp_path / "o.json"
    assert e.main(["--oracle", "--names", "func_8000825C", "--out", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["summary"]["matched"] == 0 and report["results"][0]["steps"] == 0


@needs_demo
def test_the_spending_cap_skips_the_rest_and_a_skipped_function_is_not_a_miss(tmp_path):
    out = tmp_path / "capped.json"
    assert e.main(["--oracle", "--max-usd", "0.0025", "--out", str(out)]) == 0  # one function costs 3 requests of 0.001
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [bool(r.get("skipped")) for r in report["results"]] == [False, True] and "cap" in report["results"][1]["skipped"]
    assert report["summary"]["matched"] == 1 and report["summary"]["skipped"] == 1 and report["summary"]["attempted"] == 1


@needs_demo
def test_a_function_that_is_not_an_open_function_of_the_demo_is_refused(capsys):
    assert e.main(["--oracle", "--names", "func_00000000"]) == 2
    assert "not open functions" in capsys.readouterr().err
