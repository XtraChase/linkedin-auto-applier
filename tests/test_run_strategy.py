import json

import pytest

import run_strategy as rs


def outcome(**kw):
    o = {"scored": 0, "good": 0, "opened": 0, "open_failed": 0, "searches": 5, "skips": {}, "terms": ["A", "B"], "min_fit": 30, "best_score": None}
    o.update(kw)
    return o


@pytest.mark.parametrize("kw, cause", [
    (dict(opened=2, scored=8, good=4), "ok"),
    (dict(searches=5), "no_cards"),                                                          # nothing seen at all
    (dict(skips={"handled": 12, "not_remote": 3}), "handled"),
    (dict(skips={"handled": 2, "not_easy_apply": 6, "title": 3}), "rules"),
    (dict(scored=6, good=0, best_score=24, skips={"handled": 9}), "below_cutoff"),
    (dict(scored=6, good=3, open_failed=3), "open_failures"),
    (dict(scored=2, good=2, open_failed=2), "open_failures"),
    # the real run that was misread: 47 jobs seen, 36 already handled, one new job whose form did not open
    (dict(scored=1, good=1, open_failed=1, skips={"handled": 36, "not_remote": 11}), "handled"),
    (dict(scored=1, good=1, open_failed=1, skips={"not_easy_apply": 8, "title": 3}), "rules"),
    (dict(scored=6, good=3, open_failed=0), "rules"),                                         # good jobs but nothing recorded as failing
])
def test_classify(kw, cause):
    assert rs.classify(outcome(**kw)) == cause


def test_streak_escalates_caps_and_resets(tmp_path):
    path = str(tmp_path / "fb.json")
    for expected in (1, 2, 3, 3, 3):
        fb = rs.record(path, outcome(skips={"handled": 9}))
        assert fb["streak"] == expected and fb["last_cause"] == "handled"
    fb = rs.record(path, outcome(opened=1, scored=3, good=1, terms=["Z"]))                    # one form opened: back to the normal search
    assert fb["streak"] == 0 and fb["last_cause"] == "" and fb["tried_terms"] == ["Z"]
    assert rs.load(path)["streak"] == 0


@pytest.mark.parametrize("extra", [dict(list_only=True), dict(capped=True), dict(quit=True), dict(ai_failed=True)])
def test_runs_that_say_nothing_about_the_search_do_not_count(tmp_path, extra):
    path = str(tmp_path / "fb.json")
    fb = rs.record(path, outcome(skips={"handled": 9}, **extra))
    assert fb["streak"] == 0 and fb["runs"] == []


def test_open_failures_do_not_escalate_but_leave_a_hint(tmp_path):
    path = str(tmp_path / "fb.json")
    rs.record(path, outcome(skips={"handled": 9}))                                            # streak 1
    fb = rs.record(path, outcome(scored=4, good=2, open_failed=2))                            # two or more pages that would not open
    assert fb["streak"] == 1 and fb["last_cause"] == "open_failures" and "Check LinkedIn still works" in fb["last_hint"]


def test_tried_terms_accumulate_without_duplicates_and_are_capped(tmp_path):
    path = str(tmp_path / "fb.json")
    rs.record(path, outcome(skips={"handled": 5}, terms=["CAD Drafter", "BIM"]))
    fb = rs.record(path, outcome(skips={"handled": 5}, terms=["cad drafter", "Revit Tech"]))
    assert fb["tried_terms"] == ["CAD Drafter", "BIM", "Revit Tech"]
    fb = rs.record(path, outcome(skips={"handled": 5}, terms=[f"T{i}" for i in range(60)]))
    assert len(fb["tried_terms"]) == rs.MAX_TRIED_TERMS and fb["tried_terms"][-1] == "T59"


def test_plan_adds_one_lever_group_per_empty_run():
    fb = rs.empty_feedback()
    p = rs.plan(fb, 8, 30, 10)
    assert (p.level, p.steps, p.per_term, p.candidates, p.ai_terms) == (0, [], 8, 30, 10)
    fb.update(streak=1, last_cause="handled", tried_terms=["X", "Y"])
    p = rs.plan(fb, 8, 30, 10)
    assert p.level == 1 and p.avoid_terms == ["X", "Y"] and (p.per_term, p.candidates, p.ai_terms) == (16, 45, 14)
    assert not p.relevance and not p.any_time and not p.config_terms
    fb["streak"] = 2
    p = rs.plan(fb, 8, 30, 10)
    assert p.relevance and not p.any_time
    fb["streak"] = 3
    p = rs.plan(fb, 8, 30, 10)
    assert p.relevance and p.any_time and p.config_terms and len(p.steps) == 3
    fb["streak"] = 9                                                                           # never past the top level
    assert rs.plan(fb, 8, 30, 10).level == rs.MAX_LEVEL


def test_plan_caps_depth_and_starts_wide_when_there_were_no_results():
    fb = rs.empty_feedback(); fb.update(streak=1, last_cause="no_cards")
    p = rs.plan(fb, 8, 30, 10)
    assert p.any_time and p.config_terms and not p.avoid_terms and p.per_term == 8              # widest pool first, titles later
    fb.update(streak=3, last_cause="handled")
    p = rs.plan(fb, 15, 50, 14)
    assert (p.per_term, p.candidates, p.ai_terms) == (20, 60, 16)


def test_plan_never_touches_the_users_own_rules():
    fb = rs.empty_feedback(); fb.update(streak=3, last_cause="below_cutoff", last_hint="not lowered")
    p = rs.plan(fb, 8, 30, 10)
    assert not hasattr(p, "min_fit") and not hasattr(p, "max_years") and not hasattr(p, "allow_senior")
    text = "\n".join(rs.describe(p))
    assert "unchanged" in text and "not lowered" in text


def test_hint_for_below_cutoff_names_the_numbers_and_does_not_change_them():
    h = rs.hint_for("below_cutoff", outcome(best_score=24, min_fit=30))
    assert "24" in h and "30" in h and "not lowered automatically" in h


def test_describe_is_quiet_on_a_normal_run_and_explains_a_changed_one():
    assert rs.describe(rs.plan(rs.empty_feedback(), 8, 30, 10)) == []
    fb = rs.empty_feedback(); fb.update(streak=1, last_cause="handled")
    lines = rs.describe(rs.plan(fb, 8, 30, 10))
    assert "different approach" in lines[0] and "already handled" in lines[0] and "level 1 of 3" in lines[0]


def test_load_survives_missing_or_damaged_files(tmp_path):
    assert rs.load(str(tmp_path / "none.json")) == rs.empty_feedback()
    bad = tmp_path / "bad.json"; bad.write_text("{not json", encoding="utf-8")
    assert rs.load(str(bad)) == rs.empty_feedback()
    odd = tmp_path / "odd.json"; odd.write_text(json.dumps({"streak": "three", "tried_terms": "x", "extra": 1}), encoding="utf-8")
    assert rs.load(str(odd)) == rs.empty_feedback()
