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


def test_card_list_is_read_again_when_linkedin_redraws_it(h, monkeypatch):
    from selenium.common.exceptions import StaleElementReferenceException
    monkeypatch.setattr(h.time, "sleep", lambda *_: None)
    good = [MagicMock(), MagicMock()]
    good[0].get_attribute.return_value = "job-card-component-ref-111"
    good[1].get_attribute.return_value = "job-card-component-ref-222"
    stale = MagicMock(); stale.get_attribute.side_effect = StaleElementReferenceException("gone")
    h.d = MagicMock(); h.d.find_elements.side_effect = [[stale], [stale, good[1]], good]
    assert h.list_card_ids() == ["111", "222"]                                                  # used to end the whole search
    h.d.find_elements.side_effect = lambda *a: [stale]
    with pytest.raises(StaleElementReferenceException):                                          # but not forever
        h.list_card_ids(tries=3)


def _form_driver(h, monkeypatch, dialog_answers):
    monkeypatch.setattr(h.time, "sleep", lambda *_: None)
    monkeypatch.setattr(h, "announce_job", lambda *a, **k: None)
    monkeypatch.setattr(h, "visible", lambda els: els)
    h.d = MagicMock(); h.d.execute_script.return_value = ""; h.d.find_elements.return_value = [MagicMock()]
    answers = iter(dialog_answers)
    monkeypatch.setattr(h, "dialog_text", lambda: next(answers, None))
    h.args.manual = True                                      # stop after the form opens: this test is about opening it
    return lambda: sum(1 for c in h.d.execute_script.call_args_list if "click()" in str(c.args[0]))


def test_easy_apply_is_clicked_again_when_the_first_click_is_swallowed(h, monkeypatch, capsys):
    clicks = _form_driver(h, monkeypatch, [None] * 20 + ["Apply to ALTEN"])                    # nothing after click 1, form after click 2
    assert h.hand_over_form({"id": "1", "title": "t", "company": "c"}) == "form closed, not submitted"
    assert clicks() == 2 and "clicking it again" in capsys.readouterr().out


def test_form_that_never_opens_is_reported_after_three_clicks(h, monkeypatch, capsys):
    clicks = _form_driver(h, monkeypatch, [])
    assert h.hand_over_form({"id": "1", "title": "t", "company": "c"}) == "form did not open"
    assert clicks() == 3 and "no application form appeared" in capsys.readouterr().out


def test_no_button_still_reports_no_easy_apply_button(h, monkeypatch):
    clicks = _form_driver(h, monkeypatch, [])
    monkeypatch.setattr(h, "visible", lambda els: [])
    assert h.hand_over_form({"id": "1", "title": "t", "company": "c"}) == "no Easy Apply button" and clicks() == 0
