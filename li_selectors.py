"""
Every LinkedIn page selector the bot depends on, in one place.

LinkedIn changes its pages without warning (that is why the original bot stopped working in 2026).
The offline tests (tests/test_page_fixtures.py) and the live check (health_check.py) both use THESE
definitions, so when a selector breaks you fix it here once.
"""
import re

# ---- search results page --------------------------------------------------------------------
CARD_CSS = 'div[role="button"][componentkey^="job-card-component-ref-"]'
NEXT_PAGE_CSS = 'button[data-testid="pagination-controls-next-button-visible"]'
APPLY_BTN_CSS = "button[aria-label='Easy Apply to this job']"
ABOUT_COMPANY_FMT = '[componentkey="JobDetails_AboutTheCompany_{jid}"]'

READ_CARD_JS = """
const c = arguments[0];
const ps = [...c.querySelectorAll('p')].map(p => p.innerText.trim()).filter(Boolean);
const t = c.querySelector('p span[aria-hidden="true"]');
const title = t && t.firstChild ? t.firstChild.textContent.trim() : (ps[0] || '');
return {title: title, lines: ps, text: c.innerText};
"""

DESC_JS = """
const h = [...document.querySelectorAll('h2')].find(x => x.innerText.trim() === 'About the job');
return h ? h.parentElement.parentElement.innerText : '';
"""

DETAILS_FOR_JS = """
// true once the right-hand pane shows THIS job (a JobDetails component keyed with its id) and the description text has rendered
const id = arguments[0];
if (!document.querySelector('[componentkey^="JobDetails"][componentkey$="_' + id + '"]')) return null;
const h = [...document.querySelectorAll('h2')].find(x => x.innerText.trim() === 'About the job');
if (!h) return null;
const t = h.parentElement.parentElement.innerText;
return t.length > 120 ? t : null;
"""


from selenium.common.exceptions import StaleElementReferenceException


def visible(elements):
    """The displayed ones among `elements`. LinkedIn redraws parts of the page constantly, so an element can go stale
    between finding it and asking whether it is displayed; such elements are simply skipped."""
    out = []
    for e in elements:
        try:
            if e.is_displayed(): out.append(e)
        except StaleElementReferenceException:
            continue
    return out


def parse_card(job_id, info):
    """Turn the raw card read (READ_CARD_JS) into a job dict. lines[0] is the title paragraph
    (screen-reader text + visible title); company and location follow it."""
    lines = info["lines"]
    title = info["title"] or (lines[0] if lines else "")
    rest = lines[1:]
    return {"id": job_id, "title": title, "company": rest[0] if rest else "",
            "location": rest[1] if len(rest) > 1 else "", "card_text": info["text"],
            "applied": any(re.match(r"^Applied\b", l) for l in lines)}
