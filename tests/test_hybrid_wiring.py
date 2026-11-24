"""hybrid_apply.py's run-to-run approach change, with a stand-in browser: the real smart_main wrapper and build_url levers."""
import importlib.util, os, sys, types
from unittest.mock import MagicMock

import pytest

import run_strategy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def h(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                      # hybrid_apply does os.chdir(home) when imported; pytest restores the old folder
    monkeypatch.setattr(sys, "argv", ["hybrid_apply.py"])
    stub = types.ModuleType("runAiBot"); stub.driver = MagicMock(); stub.file_name = str(tmp_path / "none.csv")
    monkeypatch.setitem(sys.modules, "runAiBot", stub)
    spec = importlib.util.spec_from_file_location("hybrid_apply_under_test", os.path.join(ROOT, "hybrid_apply.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "FEEDBACK", str(tmp_path / "run_feedback.json"))
    return mod


def fake_run(h, monkeypatch, calls, **stats):
    """Replace the body of a smart run with one that records what it was given and leaves these stats behind."""
    def body(done_ids, avoid=()):
        calls.append({"avoid": list(avoid), "per_term": h.args.per_term, "candidates": h.args.candidates, "config_terms": h.args.config_terms,
                      "relevance": h.RELEVANCE, "any_time": h.ANY_TIME})
        h.STATS.clear(); h.SKIPS.clear()
        h.SKIPS.update(stats.pop("skips", {}))
        h.STATS.update(stats); h.RUN_TERMS[:] = ["CAD Drafter", f"Title {len(calls)}"]
    monkeypatch.setattr(h, "_smart_main", body)


def test_build_url_levers(h):
    base = h.build_url("CAD Drafter")
    assert "sortBy=DD" in base and "f_TPR=" in base
    h.RELEVANCE = h.ANY_TIME = True
    wide = h.build_url("CAD Drafter")
    assert "sortBy=DD" not in wide and "f_TPR=" not in wide
    assert "f_AL=true" in wide and "f_WT=2" in wide and "keywords=CAD%20Drafter" in wide      # Easy Apply and Remote stay on


def test_empty_runs_escalate_then_a_success_resets(h, monkeypatch, capsys):
    calls = []
    for i in range(3):
        fake_run(h, monkeypatch, calls, skips={"handled": 9}, scored=0, searches=5)
        h.smart_main(set())
    assert calls[0]["per_term"] == 8 and not calls[0]["avoid"]                                # first run: the normal search
    assert calls[1]["per_term"] == 16 and calls[1]["candidates"] == 45 and "CAD Drafter" in calls[1]["avoid"]
    assert calls[2]["relevance"] and not calls[2]["any_time"]
    out = capsys.readouterr().out
    assert out.count("takes a different approach") == 2 and "next run will take a different approach" in out
    assert run_strategy.load(h.FEEDBACK)["streak"] == 3
    h.args.per_term, h.args.candidates, h.args.ai_terms = 8, 30, 10                           # (a real run starts from the flags again)
    fake_run(h, monkeypatch, calls, scored=5, good=2, opened=1, best_score=70)
    h.smart_main(set())
    assert run_strategy.load(h.FEEDBACK)["streak"] == 0


def test_no_adapt_flag_neither_changes_nor_records(h, monkeypatch):
    h.args.no_adapt = True
    calls = []
    fake_run(h, monkeypatch, calls, skips={"handled": 9})
    h.smart_main(set()); h.smart_main(set())
    assert [c["per_term"] for c in calls] == [8, 8] and not os.path.exists(h.FEEDBACK)


def test_list_only_and_capped_runs_do_not_count(h, monkeypatch):
    calls = []
    for flag in ("list_only", "capped", "quit"):
        fake_run(h, monkeypatch, calls, skips={"handled": 9}, **{flag: 1})
        h.smart_main(set())
    assert run_strategy.load(h.FEEDBACK)["streak"] == 0


def test_below_cutoff_prints_a_suggestion_and_keeps_the_users_minimum(h, monkeypatch, capsys):
    calls = []
    fake_run(h, monkeypatch, calls, scored=6, good=0, best_score=24)
    h.smart_main(set())
    fake_run(h, monkeypatch, calls, scored=6, good=0, best_score=24)
    h.smart_main(set())
    out = capsys.readouterr().out
    assert "best fit last time was 24" in out and "not lowered automatically" in out
    assert h.args.min_fit == 30
