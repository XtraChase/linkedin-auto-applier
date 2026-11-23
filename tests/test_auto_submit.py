"""Auto-submit is opt-in and holds back risky applications. The Filler is driven with a fake browser."""
import re

import answer_audit
from answer_audit import review_reasons, risk_flags
from form_filler import Filler


def row(q, a, source):
    return {"q": q, "a": a, "source": source, "flags": risk_flags(q, a, source)}


def test_review_reasons_only_count_ai_and_guessed_answers():
    assert review_reasons([row("Are you authorized to work in the US?", "Yes", "config"),
                           row("How many years of Revit?", "3", "memory"),
                           row("Why this role?", "I enjoy drafting.", "ai")]) == []
    r = review_reasons([row("Do you have a bachelor's degree?", "Yes", "ai")])
    assert r and "education" in r[0]
    r = review_reasons([row("Years of AutoCAD", "3", "default-years")])
    assert r and "default years" in r[0]
    assert review_reasons([row("Years of AutoCAD", "3", "config")]) == []
    assert "left blank" in review_reasons([], ["Salary expectation"])[0]


class FakeDriver:
    """Plays the end of an application: a Submit button, then LinkedIn's 'Application sent' dialog."""
    def __init__(self, confirm=True):
        self.clicked, self.confirm, self.submitted = [], confirm, False

    def execute_script(self, script, *args):
        if "innerText.trim()===arguments[0]" in script:
            self.clicked.append(args[0])
            if args[0] == "Submit application": self.submitted = True
            return True
        if "querySelector('dialog'); return x? x.innerText" in script:
            return "Your application was sent" if (self.submitted and self.confirm) else ("Review your application" if not self.submitted or not self.confirm else None)
        if "return !!document.querySelector('dialog')" in script:
            return False
        return None


def make(driver, **kw):
    f = Filler(driver, log=lambda *a: None, **kw)
    return f


def test_auto_submit_clicks_submit_and_closes_the_confirmation(monkeypatch):
    monkeypatch.setattr("form_filler.time.sleep", lambda s: None)
    monkeypatch.setattr("form_filler.write_log", lambda *a, **k: None)
    d = FakeDriver(); f = make(d, auto_submit=True)
    f.rec("Why this role?", "I enjoy drafting.", "ai")
    assert f._auto_submit(0, 60) == "applied"
    assert d.clicked[0] == "Submit application" and "Done" in d.clicked


def test_auto_submit_holds_back_and_does_not_click_when_an_answer_needs_a_look(monkeypatch):
    monkeypatch.setattr("form_filler.time.sleep", lambda s: None)
    monkeypatch.setattr("form_filler.write_log", lambda *a, **k: None)
    d = FakeDriver(); f = make(d, auto_submit=True)
    f.rec("Do you have a bachelor's degree?", "Yes", "ai")
    monkeypatch.setattr(f, "_wait_closed", lambda t0, limit: "stopped at review (closed, not submitted)")
    assert f._auto_submit(0, 60).startswith("stopped at review")
    assert "Submit application" not in d.clicked
    f2 = make(FakeDriver(), auto_submit=True, review_pause=False)                      # user turned the safety off
    f2.rec("Do you have a bachelor's degree?", "Yes", "ai")
    assert f2._auto_submit(0, 60) == "applied"


def test_auto_submit_not_confirmed_falls_back_to_waiting_for_you(monkeypatch):
    monkeypatch.setattr("form_filler.time.sleep", lambda s: None)
    monkeypatch.setattr("form_filler.write_log", lambda *a, **k: None)
    d = FakeDriver(confirm=False); f = make(d, auto_submit=True)
    monkeypatch.setattr(f, "_wait_closed", lambda t0, limit: "stopped at review (closed, not submitted)")
    assert f._auto_submit(0, 60).startswith("stopped at review")


def test_default_filler_never_auto_submits():
    assert Filler(FakeDriver(), log=lambda *a: None).auto_submit is False
