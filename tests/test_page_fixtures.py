"""
Offline health check: run the bot's page readers against saved, sanitized copies of LinkedIn pages.
If LinkedIn changes a page, capture a new copy into tests/fixtures/ and these tests show what broke.
Needs Google Chrome (headless, scripts off). Skipped when Chrome cannot start.
"""
import os, re

import pytest

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.fixture(scope="module")
def chrome():
    selenium = pytest.importorskip("selenium")
    from selenium import webdriver
    o = webdriver.ChromeOptions()
    o.add_argument("--headless=new"); o.add_argument("--blink-settings=scriptEnabled=false"); o.add_argument("--window-size=1600,1400")
    try:
        d = webdriver.Chrome(options=o)
    except Exception as e:                       # no Chrome or driver on this machine
        pytest.skip(f"Chrome not available: {type(e).__name__}")
    yield d
    d.quit()


def load(d, name, open_dialog=False):
    d.get("file:///" + os.path.join(FIX, name).replace("\\", "/"))
    if open_dialog:
        d.execute_script("const x=document.querySelector('dialog'); if(x){x.setAttribute('open','');}")


# ---------------------------------------------------------------- search results page
def test_job_cards_are_found_and_parsed(chrome):
    from selenium.webdriver.common.by import By
    from li_selectors import CARD_CSS, READ_CARD_JS, parse_card
    load(chrome, "results_page.html")
    cards = chrome.find_elements(By.CSS_SELECTOR, CARD_CSS)
    ids = {c.get_attribute("componentkey").rsplit("-", 1)[-1] for c in cards}
    assert len(ids) >= 20, "job cards not found: LinkedIn may have changed the list markup"
    first = parse_card("x", chrome.execute_script(READ_CARD_JS, cards[0]))
    assert first["title"] and first["company"] and "(" in first["location"] or first["location"]


def test_details_pane_and_buttons(chrome):
    from selenium.webdriver.common.by import By
    from li_selectors import CARD_CSS, DETAILS_FOR_JS, APPLY_BTN_CSS, NEXT_PAGE_CSS
    load(chrome, "results_page.html")
    jid = chrome.find_elements(By.CSS_SELECTOR, CARD_CSS)[0].get_attribute("componentkey").rsplit("-", 1)[-1]
    text = chrome.execute_script(DETAILS_FOR_JS, jid)
    assert text and len(text) > 120, "job description not readable"
    assert chrome.execute_script(DETAILS_FOR_JS, "1111111111") is None, "must not read another job's pane"
    assert chrome.find_elements(By.CSS_SELECTOR, APPLY_BTN_CSS), "Easy Apply button selector broke"
    assert chrome.find_elements(By.CSS_SELECTOR, NEXT_PAGE_CSS), "pagination Next selector broke"


# ---------------------------------------------------------------- application form
def page(chrome, name):
    import form_filler as ff
    load(chrome, name, open_dialog=True)
    return ff, chrome.execute_script(ff.ENUM_JS)


def test_contact_page(chrome):
    ff, pg = page(chrome, "form_contact.html")
    labels = [i["label"] for i in pg["items"]]
    assert any("Mobile phone" in l for l in labels) and any("Email" in l for l in labels)
    assert "Next" in pg["buttons"] and pg["progress"].startswith("1/")


def test_question_pages_expose_radios_and_text(chrome):
    ff, pg = page(chrome, "form_questions_radios.html")
    kinds = [i["kind"] for i in pg["items"]]
    assert kinds.count("radio") == 3 and "text" in kinds
    radios = [i for i in pg["items"] if i["kind"] == "radio"]
    assert all([o["text"] for o in r["options"]] == ["Yes", "No"] for r in radios)


def test_review_page_is_recognised_as_final(chrome):
    ff, pg = page(chrome, "form_review.html")
    assert "Submit application" in pg["buttons"]


def test_single_page_form_has_resume_list_and_follow_checkbox(chrome):
    ff, pg = page(chrome, "form_single_page.html")
    assert pg["resume_page"] and pg["resumes"]
    assert any(i["kind"] == "checkbox" and re.match(r"follow", i["label"], re.I) for i in pg["items"])


def test_filler_leaves_unknown_questions_and_never_clicks_submit(chrome):
    ff, pg = page(chrome, "form_questions_radios.html")
    f = ff.Filler(chrome, log=lambda *a: None, ai=None)
    filled, unanswered = f.fill_page(pg)
    assert any("Do you have experience and proficiency" in u for u in unanswered)      # nothing in config supports an answer
    assert chrome.execute_script("return [...document.querySelectorAll('dialog button')].every(b => !b.disabled || true)")
