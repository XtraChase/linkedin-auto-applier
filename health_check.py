"""
Live health check: does LinkedIn's current page still match what the bot expects?

    .venv\\Scripts\\python.exe health_check.py

Opens the bot's Chrome, signs in, runs one search and checks each selector in li_selectors.py.
It reads pages only: it never opens an application form and never submits anything.
Each line says PASS or FAIL and, on FAIL, where to look. Offline version: pytest tests/test_page_fixtures.py
"""
import sys, time

import runAiBot as bot
from selenium.webdriver.common.by import By

from li_selectors import (CARD_CSS, NEXT_PAGE_CSS, APPLY_BTN_CSS, READ_CARD_JS, DETAILS_FOR_JS, parse_card)

d = bot.driver
results = []


def check(name, ok, hint=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"   -> {hint}"))


try:
    bot.login_LN()
    d.get("https://www.linkedin.com/jobs/search/?keywords=CAD%20Drafter&location=United%20States&f_AL=true&f_WT=2")
    for _ in range(40):
        if d.find_elements(By.CSS_SELECTOR, CARD_CSS): break
        time.sleep(0.5)
    time.sleep(1)
    cards = d.find_elements(By.CSS_SELECTOR, CARD_CSS)
    check("job cards found", len(cards) >= 5, "li_selectors.CARD_CSS no longer matches the results list")
    if cards:
        jid = cards[0].get_attribute("componentkey").rsplit("-", 1)[-1]
        job = parse_card(jid, d.execute_script(READ_CARD_JS, cards[0]))
        check("card title/company/location read", bool(job["title"] and job["company"] and job["location"]), "READ_CARD_JS / parse_card: card layout changed")
        d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", cards[0])
        text = None
        for _ in range(30):
            text = d.execute_script(DETAILS_FOR_JS, jid)
            if text: break
            time.sleep(0.4)
        check("job description read for the clicked job", bool(text), "DETAILS_FOR_JS: details pane markup changed")
        check("Easy Apply button found", bool([b for b in d.find_elements(By.CSS_SELECTOR, APPLY_BTN_CSS) if b.is_displayed()]),
              "APPLY_BTN_CSS: the button label changed (or this job is not Easy Apply)")
    check("next-page button found", bool(d.find_elements(By.CSS_SELECTOR, NEXT_PAGE_CSS)), "NEXT_PAGE_CSS: pagination markup changed")
except Exception as e:
    check(f"health check ran ({type(e).__name__})", False, str(e)[:150])
finally:
    try: d.quit()
    except Exception: pass

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if results and all(results) else 1)
