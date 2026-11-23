"""End to end: the real Filler drives a real (headless) Chrome through a small stand-in for LinkedIn's multi-page Easy Apply dialog.
This is the closest offline check of the whole flow: fill the contact page, answer a question, reach Submit, and either stop or auto-submit."""
import pytest

pytest.importorskip("selenium")

PAGE = r"""<!doctype html><html><body>
<dialog open>
 <button type="button" aria-label="Dismiss"></button>
 <h2>Apply to Demo Co</h2>
 <div id="body"></div>
</dialog>
<script>
// like LinkedIn, only the current page is in the document: each step replaces the previous one
const PAGES = {
  p1: '<label for="fn">First name</label><input id="fn" type="text" required>' +
      '<label for="ph">Mobile phone number</label><input id="ph" type="text" required>' +
      '<button type="button" onclick="go(\'p2\')">Next</button>',
  p2: '<div><p>Are you legally authorized to work in the United States?</p>' +
      '<div><input type="radio" name="auth"><span>Yes</span></div><div><input type="radio" name="auth"><span>No</span></div></div>' +
      'EXTRA<button type="button" onclick="go(\'p3\')">Review</button>',
  p3: '<p>Review your application</p><button type="button" onclick="send()">Submit application</button>',
  done: '<p>Your application was sent to Demo Co</p><button type="button" onclick="document.querySelector(\'dialog\').remove()">Done</button>'
};
function go(id){ document.getElementById('body').innerHTML = PAGES[id]; }
function send(){ window.__submitted = true; go('done'); }
go('p1');
</script></body></html>"""

DEGREE = ('<div><p>Do you have a Bachelor’s degree in Architecture?</p>'
          '<div><input type="radio" name="deg"><span>Yes</span></div><div><input type="radio" name="deg"><span>No</span></div></div>')


@pytest.fixture(scope="module")
def chrome():
    from selenium import webdriver
    o = webdriver.ChromeOptions()
    o.add_argument("--headless=new"); o.add_argument("--window-size=1400,1200")
    try:
        d = webdriver.Chrome(options=o)
    except Exception as e:
        pytest.skip(f"Chrome not available: {type(e).__name__}")
    yield d
    d.quit()


def load(d, tmp_path, extra=""):
    f = tmp_path / "flow.html"
    f.write_text(PAGE.replace("EXTRA", extra), encoding="utf-8")
    d.get(f.as_uri())


def make(d, monkeypatch, tmp_path, **kw):
    import form_filler
    monkeypatch.setattr(form_filler, "write_log", lambda *a, **k: None)         # no audit file from tests
    lines = []
    f = form_filler.Filler(d, log=lambda *a: lines.append(" ".join(str(x) for x in a)), job={"id": "1", "title": "CAD Drafter", "company": "Demo Co"}, **kw)
    return f, lines


def test_default_run_stops_at_submit_and_never_clicks_it(chrome, monkeypatch, tmp_path):
    load(chrome, tmp_path)
    f, lines = make(chrome, monkeypatch, tmp_path)
    result = f.run(wait_seconds=14)                         # reaches the Submit page, then waits for a human until the limit
    assert result.startswith("stopped at review")
    assert chrome.execute_script("return !!window.__submitted") is False
    assert any("SUBMIT PAGE reached" in l for l in lines)
    assert "Submit application" in chrome.execute_script("return document.querySelector('dialog').innerText")   # still sitting on the review page


def test_auto_submit_fills_submits_and_closes(chrome, monkeypatch, tmp_path):
    load(chrome, tmp_path)
    f, lines = make(chrome, monkeypatch, tmp_path, auto_submit=True)
    assert f.run(wait_seconds=40) == "applied"
    assert chrome.execute_script("return !!window.__submitted") is True
    assert chrome.execute_script("return !!document.querySelector('dialog')") is False        # confirmation closed, ready for the next job
    assert any("AUTO-SUBMIT: submitting" in l for l in lines) and any("Application sent" in l for l in lines)


def test_auto_submit_is_held_back_when_a_question_could_not_be_answered(chrome, monkeypatch, tmp_path):
    load(chrome, tmp_path, DEGREE)                          # nothing in the config answers this degree question
    f, lines = make(chrome, monkeypatch, tmp_path, auto_submit=True)
    result = f.run(wait_seconds=20)
    assert result.startswith("stopped at review")
    assert chrome.execute_script("return !!window.__submitted") is False
    assert any("AUTO-SUBMIT HELD BACK" in l for l in lines)
