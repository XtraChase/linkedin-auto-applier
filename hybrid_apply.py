"""
Hybrid LinkedIn helper (works with LinkedIn's 2026 jobs layout).

What it does
  * Logs in with the bot's normal Chrome session (credentials / profile from config).
  * Searches each term in config/search.py using LinkedIn URL filters (Easy Apply,
    Remote, date posted, location ...), instead of clicking the filter panel.
  * Reads each job card + description, skips jobs that hit your skip words or that
    you already handled, then OPENS the Easy Apply form for you.
  * YOU fill in the questions, review and click Submit. The script never clicks
    Next, Review or Submit and never types into the form.
  * Logs every job it showed you to "all excels/hybrid_history.csv".

Usage (from this folder):
    .venv\\Scripts\\python.exe hybrid_apply.py --max-jobs 5
    .venv\\Scripts\\python.exe hybrid_apply.py --list-only --max-jobs 10   (no forms opened)
"""
import argparse, csv, json, os, re, sys, time, random
from datetime import datetime
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app_paths import home
HERE = home()
os.chdir(HERE)
sys.path.insert(0, HERE)

from app_settings import SETTINGS
ap = argparse.ArgumentParser()
ap.add_argument("--max-jobs", type=int, default=SETTINGS["max_jobs"], help="stop after opening this many Easy Apply forms (default 5)")
ap.add_argument("--list-only", action="store_true", help="only list matching jobs, never open a form")
ap.add_argument("--terms", nargs="*", help="override search terms from config/search.py")
ap.add_argument("--per-term", type=int, default=SETTINGS["per_term"], help="max jobs examined per search term (default 15)")
ap.add_argument("--manual", action="store_true", help="don't auto-fill the form; just open it and wait for you")
ap.add_argument("--no-ai", action="store_true", help="fill only from your config answers; no AI-written answers")
ap.add_argument("--sequential", action="store_true", help="old behaviour: take jobs in LinkedIn's order instead of ranking by AI fit")
ap.add_argument("--min-fit", type=int, default=SETTINGS["min_fit"], help="smart mode: only apply to jobs the AI scores at or above this (default 30)")
ap.add_argument("--candidates", type=int, default=SETTINGS["candidates"], help="smart mode: how many jobs to score before applying (default 30)")
ap.add_argument("--ai-terms", type=int, default=SETTINGS["ai_terms"], help="smart mode: how many search titles the AI chooses from your profile (default 10)")
ap.add_argument("--config-terms", action="store_true", help="smart mode: also search the titles in config/search.py")
ap.add_argument("--retry-low", action="store_true", help="smart mode: score again the jobs earlier logged as 'low fit'")
ap.add_argument("--daily-cap", type=int, default=SETTINGS["daily_cap"], help="stop opening forms after this many submitted applications today (0 = no cap)")
ap.add_argument("--any-level", action="store_true", help="smart mode: don't limit to entry-level / associate postings")
ap.add_argument("--auto-submit", action="store_true", help="OPT-IN: click Submit for you when the application has nothing that needs a look, then move on to the next form")
ap.add_argument("--no-review-pause", action="store_true", help="with --auto-submit: submit even when an answer is flagged (AI-written credential/legal answers, guessed years, blanks)")
ap.add_argument("--no-adapt", action="store_true", help="smart mode: do not change the search approach after a run that opened no forms")
ap.add_argument("--job", default="", help="apply to this one LinkedIn job (a job id or a pasted job link): fill the form and stop at Submit")
ap.add_argument("--allow-senior", action="store_true", default=bool(SETTINGS["allow_senior"]), help="smart mode: don't skip Senior / Lead / Manager / Director titles")
ap.add_argument("--max-years", type=int, default=SETTINGS["max_years"], help="smart mode: skip postings that require this many years or more (default 7)")
args = ap.parse_args()

import runAiBot as bot                      # opens the bot's Chrome session; gives us login_LN()
from selenium.webdriver.common.by import By
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException, StaleElementReferenceException
from config import search as S
from form_filler import Filler
from requirements_check import title_blocker, hard_blockers

d = bot.driver
answerer = None
HISTORY = os.path.join(HERE, "all excels", "hybrid_history.csv")
os.makedirs(os.path.dirname(HISTORY), exist_ok=True)

import collections
SKIPS = collections.Counter()  # why jobs were skipped this run (see run_strategy.py)
STATS = collections.Counter()  # other facts about this run, for the next run's approach
ANY_TIME = RELEVANCE = False   # search levers a run that follows an empty one may switch on (run_strategy.plan)
FEEDBACK = os.path.join(HERE, "all excels", "run_feedback.json")

DATE_MAP = {"Past 24 hours": "r86400", "Past week": "r604800", "Past month": "r2592000"}
WT_MAP = {"On-site": "1", "Remote": "2", "Hybrid": "3"}
EXP_MAP = {"Internship": "1", "Entry level": "2", "Associate": "3", "Mid-Senior level": "4", "Director": "5", "Executive": "6"}
JT_MAP = {"Full-time": "F", "Part-time": "P", "Contract": "C", "Temporary": "T", "Volunteer": "V", "Internship": "I", "Other": "O"}


def build_url(term):
    q = [f"keywords={quote(term)}"]
    if S.search_location.strip():          q.append(f"location={quote(S.search_location.strip())}")
    if S.easy_apply_only:                  q.append("f_AL=true")
    if S.date_posted in DATE_MAP and not ANY_TIME: q.append(f"f_TPR={DATE_MAP[S.date_posted]}")
    if S.on_site:                          q.append("f_WT=" + ",".join(WT_MAP[x] for x in S.on_site if x in WT_MAP))
    levels = [] if args.any_level else (S.experience_level or SETTINGS["experience_levels"])
    if levels:                             q.append("f_E=" + ",".join(EXP_MAP[x] for x in levels if x in EXP_MAP))
    if S.job_type:                         q.append("f_JT=" + ",".join(JT_MAP[x] for x in S.job_type if x in JT_MAP))
    if (S.sort_by == "Most recent" or SETTINGS["sort_recent"]) and not RELEVANCE: q.append("sortBy=DD")
    return "https://www.linkedin.com/jobs/search/?" + "&".join(q)


def load_history():
    ids = set()
    for path in (HISTORY, bot.file_name):
        try:
            with open(path, encoding="utf-8") as f:
                for row in csv.reader(f):
                    if not row: continue
                    if args.retry_low and len(row) > 5 and row[5].startswith("low fit"): continue   # re-score these
                    ids.add(row[0])
        except FileNotFoundError:
            pass
    return ids


def log_row(job, status):
    new = not os.path.exists(HISTORY)
    with open(HISTORY, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new: w.writerow(["job_id", "title", "company", "location", "link", "status", "time"])
        w.writerow([job["id"], job["title"], job["company"], job["location"],
                    "https://www.linkedin.com/jobs/view/" + job["id"], status, datetime.now().isoformat(timespec="seconds")])


CACHE_PATH = os.path.join(HERE, "all excels", "score_cache.json")
CACHE_DAYS = 14


def load_cache():
    """Scored jobs from earlier runs (so a re-run doesn't re-open and re-score every posting)."""
    try:
        data = json.load(open(CACHE_PATH, encoding="utf-8"))
    except Exception:
        return {}
    cutoff = time.time() - CACHE_DAYS * 86400
    from ai_answers import SCORE_VERSION
    return {k: v for k, v in data.items() if v.get("ts", 0) >= cutoff and v.get("v") == SCORE_VERSION}


def save_cache():
    try:
        json.dump(SCORE_CACHE, open(CACHE_PATH, "w", encoding="utf-8"))
    except Exception:
        pass


SCORE_CACHE = {}


RUN_ENTRIES = []
SEEN_POSTINGS = set()          # (title, company) pairs already looked at in this run
REPORT_DIR = os.path.join(HERE, "reports")


def set_status(job_id, status):
    for e in RUN_ENTRIES:
        if e["id"] == job_id: e["status"] = status


def ask_outcome(result, more=True):
    """After a form closes, confirm whether it was really submitted. Returns (result, quit_now)."""
    if result == "applied" and args.auto_submit:
        print("   Recorded as APPLIED (LinkedIn showed 'Application sent'). Moving on.")
        return result, False
    if result == "applied":
        print("   Recorded as APPLIED (LinkedIn showed 'Application sent').")
        prompt = "   Press Enter to continue" + (" to the next job" if more else "") + ", or q then Enter to quit: "
    else:
        prompt = "   Did you submit it? y = yes, Enter = no, q = quit: "
    ans = input(prompt).strip().lower()
    if result != "applied" and ans.startswith("y"):
        result = "applied (confirmed by you)"
    return result, ans.startswith("q")


def write_report():
    """Write reports/run-<time>.md summarising this run (ranked jobs and what happened to each)."""
    if not RUN_ENTRIES: return
    try:
        os.makedirs(REPORT_DIR, exist_ok=True)
        path = os.path.join(REPORT_DIR, "run-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".md")
        applied = [e for e in RUN_ENTRIES if e["status"].startswith("applied")]
        opened = [e for e in RUN_ENTRIES if e["status"] not in ("queued", "below cutoff")]
        lines = [f"# Run report {datetime.now():%Y-%m-%d %H:%M}", "",
                 f"- Jobs scored: {len(RUN_ENTRIES)}",
                 f"- At or above the fit cutoff ({args.min_fit}): {len([e for e in RUN_ENTRIES if e['status'] != 'below cutoff'])}",
                 f"- Forms opened: {len(opened)}", f"- Submitted: {len(applied)}", "",
                 "| Fit | Job | Company | Outcome |", "|---:|---|---|---|"]
        for e in sorted(RUN_ENTRIES, key=lambda x: -x["score"]):
            lines.append(f"| {e['score']} | {e['title']} | {e['company']} | {e['status']} |")
        lines += ["", "AI-written answers for each application are in `all excels/answers_log.jsonl`."]
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        print("Report written:", path)
    except Exception as e:
        print("(could not write the report:", type(e).__name__, ")")


def has_word(text, words):
    t = text.lower()
    for w in words:
        w = w.strip().lower()
        if w and re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t):
            return w
    return None


from li_selectors import visible, CARD_CSS, NEXT_PAGE_CSS, APPLY_BTN_CSS, ABOUT_COMPANY_FMT, READ_CARD_JS, DESC_JS, DETAILS_FOR_JS, JOB_META_JS, parse_card


def pause(a=1.5, b=3.5):
    time.sleep(random.uniform(a, b))


def read_job(card):
    jid = card.get_attribute("componentkey").rsplit("-", 1)[-1]
    return parse_card(jid, d.execute_script(READ_CARD_JS, card))


def open_details(card, jid):
    """Click a job card and return (description, about-company). Reads as soon as the pane shows this job."""
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", card)
    desc = ""
    t0 = time.time()
    while time.time() - t0 < 9:
        desc = d.execute_script(DETAILS_FOR_JS, jid) or ""
        if desc: break
        time.sleep(0.25)
    about = ""
    for _ in range(6):                       # the company block renders a little later; give it up to ~1.5 s
        els = d.find_elements(By.CSS_SELECTOR, f'[componentkey="JobDetails_AboutTheCompany_{jid}"]')
        if els:
            about = els[0].text; break
        time.sleep(0.25)
    pause(0.2, 0.6)
    return desc or (d.execute_script(DESC_JS) or ""), about


def dialog_text():
    return d.execute_script("const x = document.querySelector('dialog'); return x ? x.innerText : null;")


CURRENT_JOB_PATH = os.path.join(HERE, "all excels", "current_job.json")


def announce_job(job, desc="", about=""):
    """Tell the desktop app which job is being applied to (a link line in the log, plus the full posting in a file)."""
    link = "https://www.linkedin.com/jobs/view/" + job["id"] + "/"
    print(f"   job-link: {link}")
    try:
        os.makedirs(os.path.dirname(CURRENT_JOB_PATH), exist_ok=True)
        json.dump({"id": job["id"], "title": job.get("title", ""), "company": job.get("company", ""), "location": job.get("location", ""),
                   "link": link, "fit": job.get("score"), "reason": job.get("reason", ""), "description": desc or job.get("description", ""),
                   "about": about or job.get("about", ""), "time": datetime.now().isoformat(timespec="seconds")},
                  open(CURRENT_JOB_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass


def hand_over_form(job, desc="", about=""):
    """Click Easy Apply, fill the form from your config + AI, stop at the Submit page. Submits only with the opt-in --auto-submit."""
    announce_job(job, desc, about)
    opened_form = False
    for click_round in range(3):             # a click can be swallowed while LinkedIn redraws the pane: click again (only once no form is showing)
        clicked = False
        for attempt in range(5):             # re-find the button each try, because the pane is redrawn right after load
            try:
                btns = visible(d.find_elements(By.CSS_SELECTOR, APPLY_BTN_CSS))
                if not btns:
                    time.sleep(1.5); continue
                d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btns[0])
                clicked = True; break
            except (InvalidSessionIdException, NoSuchWindowException):
                raise
            except Exception:
                time.sleep(1.5)
        if not clicked:
            return "no Easy Apply button"
        for _ in range(20):
            if dialog_text() is not None: opened_form = True; break
            time.sleep(0.5)
        if opened_form: break
        if click_round < 2: print("   (the form did not appear after clicking Easy Apply; clicking it again)")
    if not opened_form:
        try:                                  # say what the page shows instead, so a pattern can be spotted
            seen = d.execute_script("const x = document.querySelector('[role=dialog],[role=alertdialog],[aria-modal=true]'); return x ? x.innerText.slice(0, 200) : '';") or ""
            seen = re.sub(r"\s+", " ", seen) or "none"
            print(f"   (no application form appeared. Page: {(d.current_url or '').split('?')[0]}; popup text: {seen})")
        except Exception:
            pass
        return "form did not open"
    if not args.manual:
        if args.auto_submit:
            print("   >> Form open: filling what your config covers. AUTO-SUBMIT is ON: I will click Submit if nothing needs a look" + ("." if not args.no_review_pause else " (even if answers are flagged)."))
        else:
            print("   >> Form open: filling what your config covers. I never click Submit; you do that on the Review page.")
        if answerer is not None:
            answerer.set_job({"id": job["id"], "title": job["title"], "company": job["company"], "description": desc, "about": about})
        res = Filler(d, log=print, ai=answerer, job=job, auto_submit=args.auto_submit, review_pause=not args.no_review_pause).run()
        return {"applied": "applied", "closed": "form closed, not submitted"}.get(res, res)
    print("   >> The Easy Apply form is open. Fill it in and click Submit yourself (or close it to skip).")
    last, sent, started = "", False, time.time()
    while time.time() - started < 25 * 60:
        t = dialog_text()
        if t is None: break
        last = t
        if re.search(r"application (was )?sent|your application was sent", t, re.I): sent = True
        time.sleep(1)
    return "applied" if sent else "form closed, not submitted"


# =============================================================================================
# SMART MODE: AI picks search titles, scans results (Remote + US + Easy Apply), scores fit, applies best-first
# =============================================================================================
def list_card_ids(tries=5):
    """The job ids of the cards on the results page. LinkedIn redraws the list while it loads, which makes a card go stale
    between finding it and reading it; that used to end the whole search, so read the list again instead."""
    for attempt in range(tries):
        try:
            ids = []
            for c in d.find_elements(By.CSS_SELECTOR, CARD_CSS):
                cid = c.get_attribute("componentkey").rsplit("-", 1)[-1]
                if cid not in ids: ids.append(cid)
            return ids
        except StaleElementReferenceException:
            if attempt == tries - 1: raise
            time.sleep(0.6)


def scan_term(term, limit, done_ids, seen_all):
    """Yield (job, desc, about) for jobs on this search that pass the hard filters."""
    t_load = time.time()
    d.get(build_url(term)); wait_for_cards()
    check_blocked()
    print(f"   (results loaded in {time.time() - t_load:.0f}s)")
    examined, seen_here = 0, set()
    while examined < limit:
        card_ids = list_card_ids()
        if not card_ids:
            if not seen_here: STATS["empty_searches"] += 1
            print("  No job cards found (no results, or the page layout changed)."); return
        for cid in card_ids:
            if examined >= limit: return
            if cid in seen_here or cid in seen_all: continue
            try:
                card = d.find_element(By.CSS_SELECTOR, f'div[role="button"][componentkey="job-card-component-ref-{cid}"]')
                job = read_job(card)
            except (InvalidSessionIdException, NoSuchWindowException):
                raise
            except Exception:
                continue
            seen_here.add(cid); seen_all.add(cid); examined += 1
            tag = f'{job["title"]} | {job["company"]} | {job["location"]}'
            if cid in done_ids or job["applied"]:
                SKIPS["handled"] += 1; print(f"   - skip (already handled): {tag}"); continue
            if "easy apply" not in job["card_text"].lower():
                SKIPS["not_easy_apply"] += 1; print(f"   - skip (not Easy Apply): {tag}"); continue
            if "remote" not in job["location"].lower():
                SKIPS["not_remote"] += 1; print(f"   - skip (not marked Remote): {tag}"); continue
            why = None if args.allow_senior else title_blocker(job["title"])
            if why:
                SKIPS["title"] += 1; print(f"   - skip ({why}): {tag}"); log_row(job, f"skipped: {why}"); done_ids.add(cid); continue
            blocked = next((b for b in SETTINGS["blocked_companies"] if b and b.lower() in job["company"].lower()), None)
            if blocked:
                SKIPS["blocked_company"] += 1; print(f'   - skip (blocked company "{blocked}"): {tag}'); log_row(job, f'skipped: blocked company "{blocked}"'); done_ids.add(cid); continue
            dup_key = (job["title"].strip().lower(), job["company"].strip().lower())
            if dup_key in SEEN_POSTINGS:             # same role at the same company in another city: look at it once
                SKIPS["duplicate"] += 1; print(f"   - skip (duplicate posting): {tag}"); done_ids.add(cid); continue
            SEEN_POSTINGS.add(dup_key)
            c = SCORE_CACHE.get(cid)
            if c:                                   # scored in an earlier run: no need to open and re-score it
                blk = hard_blockers(c["description"], args.max_years)
                if blk:
                    SKIPS["hard_blockers"] += 1; print(f"   - skip ({'; '.join(blk)}): {tag}"); log_row(job, f"skipped: {'; '.join(blk)}"); done_ids.add(cid); continue
                job.update(score=c["score"], reason=c["reason"])
                yield job, c["description"], c["about"]; continue
            try:
                t_det = time.time()
                desc, about = open_details(card, cid)
                job["t_details"] = time.time() - t_det
            except (InvalidSessionIdException, NoSuchWindowException):
                raise
            except Exception:
                continue
            hit = has_word(desc, S.bad_words)
            if hit:
                SKIPS["bad_words"] += 1; print(f'   - skip (posting says "{hit}"): {tag}'); log_row(job, f'skipped: "{hit}"'); done_ids.add(cid); continue
            blk = hard_blockers(desc, args.max_years)
            if blk:
                SKIPS["hard_blockers"] += 1; print(f"   - skip ({'; '.join(blk)}): {tag}"); log_row(job, f"skipped: {'; '.join(blk)}"); done_ids.add(cid); continue
            good = has_word(about, S.about_company_good_words)
            bad = None if good else has_word(about + " " + job["company"], S.about_company_bad_words)
            if bad:
                SKIPS["company_text"] += 1; print(f'   - skip (company text "{bad}"): {tag}'); log_row(job, f'skipped: company "{bad}"'); done_ids.add(cid); continue
            yield job, desc, about
        # finished this page of cards: next page of results
        nxt = visible(d.find_elements(By.CSS_SELECTOR, NEXT_PAGE_CSS))
        if examined < limit and nxt:
            first = card_ids[0]
            # a script click, after scrolling it into view: LinkedIn overlays (job-alert bar, chat) can block a normal click
            d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", nxt[0])
            for _ in range(40):                         # wait (up to ~12 s) for the next page of results to replace the list
                try:
                    now = d.find_elements(By.CSS_SELECTOR, CARD_CSS)
                    if now and now[0].get_attribute("componentkey").rsplit("-", 1)[-1] != first: break
                except StaleElementReferenceException:       # the list was redrawn between finding and reading: look again
                    pass
                time.sleep(0.3)
            continue
        return


class Blocked(Exception):
    """LinkedIn is asking for a human: security check, captcha, or a sign-in page."""


BLOCK_URLS = ("/checkpoint/", "/authwall", "/uas/captcha", "/uas/login", "/login")
BLOCK_TEXT = re.compile(r"quick security check|security verification|verify (that )?you('| a)re (a )?human|captcha|unusual activity|we couldn.t verify", re.I)


def check_blocked():
    """Stop cleanly (instead of pushing on) when LinkedIn shows a security check or sign-in page."""
    url = (d.current_url or "").lower()
    if any(s in url for s in BLOCK_URLS):
        raise Blocked(f"LinkedIn is showing a sign-in or security page ({url.split('?')[0]})")
    try:
        txt = d.execute_script("return (document.body && document.body.innerText || '').slice(0, 1500)") or ""
    except Exception:
        txt = ""
    if BLOCK_TEXT.search(txt) and not d.find_elements(By.CSS_SELECTOR, CARD_CSS):
        raise Blocked("LinkedIn is asking you to verify you are human")


def applied_today():
    """How many applications the history log records as submitted today."""
    n, today = 0, datetime.now().strftime("%Y-%m-%d")
    try:
        with open(HISTORY, encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) > 6 and row[5].startswith("applied") and row[6].startswith(today): n += 1
    except FileNotFoundError:
        pass
    return n


def wait_for_cards(timeout=15):
    """Wait until the results list has job cards (instead of sleeping a fixed time)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if d.find_elements(By.CSS_SELECTOR, CARD_CSS):
            time.sleep(0.8); return True
        time.sleep(0.3)
    return False


def safe_scan(term, limit, done_ids, seen_all):
    """scan_term, but one search that hits an odd page ends that search only, not the whole run."""
    try:
        yield from scan_term(term, limit, done_ids, seen_all)
    except (InvalidSessionIdException, NoSuchWindowException, Blocked):
        raise
    except Exception as e:
        import traceback
        where = traceback.extract_tb(e.__traceback__)[-1]          # say where, so a repeat is easy to track down
        print(f'   (the search for "{term}" stopped early: {type(e).__name__} at {os.path.basename(where.filename)}:{where.lineno}; moving on to the next title)')


def open_job(job, direct=False):
    """Load the search with this job selected in the details pane. Returns True when its Easy Apply button is there.
    direct=True (a job that came from a pasted link) tries the job's own page first, since it may not be in any search."""
    jid = job["id"]
    urls = [build_url(job["term"]) + f"&currentJobId={jid}", f"https://www.linkedin.com/jobs/view/{jid}/"]
    for url in (urls[::-1] if direct else urls):
        d.get(url)
        check_blocked()
        for _ in range(30):
            ready = d.find_elements(By.CSS_SELECTOR, f'[componentkey="JobDetails_AboutTheCompany_{jid}"]')
            btn = visible(d.find_elements(By.CSS_SELECTOR, APPLY_BTN_CSS))
            if btn and (ready or "/jobs/view/" in d.current_url): return True
            time.sleep(0.5)
    return False


def apply_one(job_id, done_ids):
    """Auto apply to one specific job (the Jobs tab button): open it, fill the form, stop at Submit, ask what you did."""
    from job_lookup import build_job, history_row, parse_job_meta
    args.auto_submit = False                      # the Jobs tab button always pauses at Submit for you
    SCORE_CACHE.update(load_cache())
    job = build_job(job_id, SCORE_CACHE.get(job_id), history_row(job_id, HISTORY))
    known = bool(job["title"])                     # False for a job that came from a pasted link: read it from its page
    score = job["score"] if job["score"] is not None else "-"
    print(f">>> Applying to #1: [{score}] {job['title'] or 'LinkedIn job ' + job_id} | {job['company']}")
    if job["reason"]: print(f"    why: {job['reason'][:220]}")
    if not known:
        log_row(job, "added from a link")          # on the Jobs list from the start, even if the run is stopped
    try:
        page_ok = open_job(job, direct=not known)
    except (InvalidSessionIdException, NoSuchWindowException, Blocked):
        raise
    except Exception as e:
        print(f"   (could not open this job's page: {type(e).__name__})"); page_ok = False
    if not known and page_ok:
        meta = parse_job_meta(d.execute_script(JOB_META_JS))
        for k in ("title", "company", "location"): job[k] = job[k] or meta[k]
        if job["title"]: print(f"   read the job: {job['title']} | {job['company']} | {job['location']}")
    if not page_ok:
        print("   could not open this job's page with an Easy Apply button. It may be closed, already applied to, or not Easy Apply.")
        log_row(job, "could not open job page"); return
    desc, about = job["description"], job["about"]
    if not desc:                                   # not in the score cache: read it from the page that is open now
        desc = d.execute_script(DESC_JS) or ""
        els = d.find_elements(By.CSS_SELECTOR, ABOUT_COMPANY_FMT.format(jid=job_id))
        about = els[0].text if els else ""
    if job["score"] is None and answerer is not None and desc:     # a new job gets a fit score like any other, shown in the Jobs list
        job["description"], job["about"] = desc, about
        job["score"], job["reason"] = answerer.score_job(job)
        if job["score"] >= 0:
            from ai_answers import SCORE_VERSION
            SCORE_CACHE[job_id] = {"score": job["score"], "reason": job["reason"], "description": desc[:6000], "about": about[:1500],
                                   "title": job["title"], "company": job["company"], "location": job["location"], "ts": time.time(), "v": SCORE_VERSION}
            save_cache()
            print(f"   fit score: {job['score']}  {job['reason'][:200]}")
        else:
            job["score"] = None
    try:
        result = hand_over_form(job, desc, about)
    except (InvalidSessionIdException, NoSuchWindowException, Blocked):
        raise
    except Exception as e:
        result = f"error: {type(e).__name__}"
    print("   result:", result)
    if result not in ("no Easy Apply button", "form did not open") and not result.startswith("error"):
        result, _ = ask_outcome(result, False)
    log_row(job, f"{result} (auto apply from the Jobs tab)"); done_ids.add(job_id)
    print("\nDone.")


RUN_TERMS = []                 # the search titles this run used (remembered so the next empty run can pick different ones)


def smart_main(done_ids):
    """Smart mode, with a different approach after a run that opened no forms (see run_strategy.py), and a record of how this run went."""
    import run_strategy
    global ANY_TIME, RELEVANCE
    avoid = []
    if not args.no_adapt:
        p = run_strategy.plan(run_strategy.load(FEEDBACK), args.per_term, args.candidates, args.ai_terms)
        for line in run_strategy.describe(p): print(line)
        args.per_term, args.candidates, args.ai_terms = p.per_term, p.candidates, p.ai_terms
        ANY_TIME, RELEVANCE, avoid = p.any_time, p.relevance, p.avoid_terms
        if p.config_terms: args.config_terms = True
    _smart_main(done_ids, avoid)
    if args.no_adapt: return
    outcome = {"time": datetime.now().isoformat(timespec="seconds"), "skips": {k: int(v) for k, v in SKIPS.items()}, "terms": list(RUN_TERMS),
               "min_fit": args.min_fit, "scored": STATS["scored"], "good": STATS["good"], "opened": STATS["opened"],
               "open_failed": STATS["open_failed"], "searches": STATS["searches"], "empty_searches": STATS["empty_searches"],
               "best_score": STATS["best_score"] if STATS["scored"] else None,
               "list_only": bool(STATS["list_only"]), "capped": bool(STATS["capped"]), "quit": bool(STATS["quit"]),
               "ai_failed": bool(STATS["score_failed"]) and STATS["score_failed"] >= STATS["scored"]}
    fb = run_strategy.record(FEEDBACK, outcome)
    if fb["last_cause"] and run_strategy.counts_as_empty(outcome):
        if fb["last_cause"] == "open_failures":
            print("\n(This run found good jobs but none would open. That points at the LinkedIn page, not your search, so the search approach is not changed.)")
        else:
            print(f"\n(This run opened no forms ({fb['last_cause'].replace('_', ' ')}). The next run will take a different approach.)")
        if fb["last_hint"]: print("   " + fb["last_hint"])


def _smart_main(done_ids, avoid=()):
    SCORE_CACHE.update(load_cache())
    # the AI chooses the search titles from your profile (mostly drafting / CAD); config titles only if asked or as a fallback
    terms = list(args.terms) if args.terms else (list(S.search_terms) if args.config_terms else [])
    if args.ai_terms > 0:
        extra = answerer.suggest_terms(args.ai_terms, existing=terms + list(avoid))
        if extra: print("AI chose these search titles:", extra)
        terms += extra
    if not terms:
        terms = list(S.search_terms); print("AI gave no titles; using your config titles:", terms)
    RUN_TERMS[:] = terms
    print(f"\nSearching {len(terms)} titles (Remote, {S.search_location}, Easy Apply, {'any date' if ANY_TIME else S.date_posted}); up to {args.candidates} jobs scored.\n")
    cands, seen_all = [], set()
    quota = max(3, -(-args.candidates // len(terms)))      # spread the budget so every title (incl. the AI's) gets searched
    for term in terms:
        if len(cands) >= args.candidates: break
        print(f'===== "{term}" =====')
        n_term = 0; STATS["searches"] += 1
        for job, desc, about in safe_scan(term, args.per_term, done_ids, seen_all):
            t0 = time.time()
            job.update(description=desc, about=about, term=term)
            if "score" not in job:
                job["score"], job["reason"] = answerer.score_job(job)
                if job["score"] < 0: job["score"] = 0; STATS["score_failed"] += 1
                from ai_answers import SCORE_VERSION
                SCORE_CACHE[job["id"]] = {"score": job["score"], "reason": job["reason"], "description": desc[:6000],
                                          "about": about[:1500], "title": job["title"], "company": job["company"],
                                          "location": job["location"], "ts": time.time(), "v": SCORE_VERSION}
                save_cache()
            cands.append(job); n_term += 1
            print(f'   [{job["score"]:3d}] {job["title"]} | {job["company"]} | {job["location"]}  (details {job.get("t_details", 0):.0f}s, scoring {time.time() - t0:.0f}s)\n         {job["reason"][:200]}')
            if len(cands) >= args.candidates or n_term >= quota: break
    cands.sort(key=lambda j: -j["score"])
    good = [j for j in cands if j["score"] >= args.min_fit]
    STATS["scored"], STATS["good"], STATS["best_score"] = len(cands), len(good), (cands[0]["score"] if cands else 0)
    print(f"\n===== RANKED: {len(cands)} jobs scored, {len(good)} at or above fit {args.min_fit} =====")
    for i, j in enumerate(cands, 1):
        mark = "*" if j["score"] >= args.min_fit else " "
        print(f' {mark}{i:2d}. {j["score"]:3d}  {j["title"]} | {j["company"]}')
    for j in cands:
        RUN_ENTRIES.append({"id": j["id"], "title": j["title"], "company": j["company"], "score": j["score"],
                            "status": "queued" if j["score"] >= args.min_fit else "below cutoff", "reason": j["reason"]})
        if j["score"] < args.min_fit:
            log_row(j, f'low fit {j["score"]}: {j["reason"][:120]}'); done_ids.add(j["id"])
    if args.list_only:
        for j in good: log_row(j, f'listed, fit {j["score"]}'); done_ids.add(j["id"])
        STATS["list_only"] = 1
        print("\n(list-only: no forms opened)"); return
    left = args.daily_cap - applied_today()
    if left <= 0 and good:
        print(f"\nDaily cap reached: {applied_today()} applications submitted today (cap {args.daily_cap}). Not opening more forms; try again tomorrow.")
        STATS["capped"] = 1
        return
    limit = min(args.max_jobs, left) if args.daily_cap > 0 else args.max_jobs
    opened = 0
    for j in good:
        if opened >= limit: break
        print(f'\n>>> Applying to #{opened + 1}: [{j["score"]}] {j["title"]} | {j["company"]}\n    why: {j["reason"][:220]}')
        try:
            page_ok = open_job(j)
        except (InvalidSessionIdException, NoSuchWindowException, Blocked):
            raise
        except Exception as e:                  # one odd page must not end the run: skip this job and go on
            print(f"   (could not open this job's page: {type(e).__name__})"); page_ok = False
        if not page_ok:
            print("   could not open this job's page with an Easy Apply button; skipping it")
            STATS["open_failed"] += 1
            log_row(j, "could not open job page"); done_ids.add(j["id"]); continue
        try:
            result = hand_over_form(j, j["description"], j["about"])
        except (InvalidSessionIdException, NoSuchWindowException):
            raise
        except Exception as e:                # never let one odd page end the whole run
            result = f"error: {type(e).__name__}"
        print("   result:", result)
        quit_now = False
        if result in ("no Easy Apply button", "form did not open") or result.startswith("error"): STATS["open_failed"] += 1
        if result not in ("no Easy Apply button", "form did not open") and not result.startswith("error"):
            opened += 1; STATS["opened"] = opened
            more = opened < limit and any(x["score"] >= args.min_fit and x["id"] not in done_ids and x["id"] != j["id"] for x in good)
            result, quit_now = ask_outcome(result, more)
        log_row(j, f'{result} (fit {j["score"]})'); done_ids.add(j["id"]); set_status(j["id"], result)
        if quit_now: STATS["quit"] = 1; return
        if args.auto_submit and result == "applied": pause(4, 9)      # unhurried between automatic submissions
    print("\nDone. Forms opened:", opened, "| history:", HISTORY)


def main():
    if args.job:                                   # --job takes a job id or a pasted LinkedIn job link
        from job_lookup import parse_job_link
        args.job = parse_job_link(args.job)
        if not args.job:
            print("ERROR: that is not a LinkedIn job link or job id (expected something like https://www.linkedin.com/jobs/view/1234567890/)")
            return
    done_ids = load_history()
    terms = args.terms or S.search_terms
    forms_opened = 0
    global answerer
    if not args.no_ai:
        from config import secrets as SEC
        if SEC.use_AI:
            from ai_answers import AIAnswerer
            answerer = AIAnswerer(log=print)
            print("AI answers:", "ON (grounded in config/profile.md)" if answerer.ok else "OFF (AI client or profile.md unavailable)")
            if not answerer.ok: answerer = None
    print("Logging in ...")
    try:                                      # LinkedIn login from Windows Credential Manager, if you stored one
        import secure_store
        bot.username = secure_store.get("linkedin_username") or bot.username
        bot.password = secure_store.get("linkedin_password") or bot.password
    except Exception:
        pass
    bot.login_LN()
    check_blocked()
    if args.job:
        return apply_one(args.job.strip(), done_ids)
    if answerer is not None and not args.sequential:
        return smart_main(done_ids)
    for term in terms:
        if forms_opened >= args.max_jobs: break
        url = build_url(term)
        print(f'\n===== Search: "{term}" =====\n{url}')
        d.get(url); time.sleep(8)
        examined, seen_here = 0, set()
        while examined < args.per_term and forms_opened < args.max_jobs:
            card_ids = []
            for c in d.find_elements(By.CSS_SELECTOR, CARD_CSS):
                cid = c.get_attribute("componentkey").rsplit("-", 1)[-1]
                if cid not in card_ids: card_ids.append(cid)
            if not card_ids:
                print("  No job cards found on this page (page layout changed, or no results).")
                break
            for cid in card_ids:
                if examined >= args.per_term or forms_opened >= args.max_jobs: break
                if cid in seen_here: continue
                try:
                    # re-find the card each time: LinkedIn re-renders the list as we click through it
                    card = d.find_element(By.CSS_SELECTOR, f'div[role="button"][componentkey="job-card-component-ref-{cid}"]')
                    job = read_job(card)
                except (InvalidSessionIdException, NoSuchWindowException):
                    print("\n  The bot's Chrome window was closed, so I can't continue. Start the script again."); return
                except Exception as e:
                    print("  could not read a card:", repr(e)[:120]); continue
                if job["id"] in seen_here: continue
                seen_here.add(job["id"]); examined += 1
                print(f'\n[{examined}] {job["title"]} | {job["company"]} | {job["location"]}  (id {job["id"]})')
                if job["id"] in done_ids or job["applied"]:
                    print("   skip: already applied / already handled"); continue
                try:
                    desc, about = open_details(card, job["id"])
                except Exception as e:
                    print("   could not open details:", repr(e)[:120]); continue
                hit = has_word(desc, S.bad_words)
                if hit:
                    print(f'   skip: description contains "{hit}"'); log_row(job, f'skipped: "{hit}"'); done_ids.add(job["id"]); continue
                good = has_word(about, S.about_company_good_words)
                bad = None if good else has_word(about + " " + job["company"], S.about_company_bad_words)
                if bad:
                    print(f'   skip: company text contains "{bad}"'); log_row(job, f'skipped: company "{bad}"'); done_ids.add(job["id"]); continue
                print("   description:", re.sub(r"\s+", " ", desc)[:200] or "(not read)")
                if args.list_only:
                    log_row(job, "listed"); done_ids.add(job["id"]); continue
                result = hand_over_form(job, desc, about)
                print("   result:", result)
                quit_now = False
                if result not in ("no Easy Apply button", "form did not open"):
                    forms_opened += 1
                    result, quit_now = ask_outcome(result, forms_opened < args.max_jobs)
                log_row(job, result); done_ids.add(job["id"])
                if quit_now: return
                pause()
            else:
                # finished this page of cards: go to the next page of results if any
                nxt = visible(d.find_elements(By.CSS_SELECTOR, NEXT_PAGE_CSS))
                if examined < args.per_term and nxt:
                    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", nxt[0]); time.sleep(6); continue
            break
    print("\nDone. Forms opened:", forms_opened, "| history:", HISTORY)


# (the guard lets the tests import this file without starting a run)
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped by you.")
    except Blocked as e:
        print(f"\nSTOPPED: {e}.\nSolve it in the bot's Chrome window if you can, wait a while, then start again. The bot does not try to get past security checks.")
    except (InvalidSessionIdException, NoSuchWindowException):
        print("\nThe bot's Chrome window was closed, so the script stopped. Start it again to continue.")
    finally:
        write_report()
        try: d.quit()
        except Exception: pass
