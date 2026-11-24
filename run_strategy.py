"""
Change the search approach after a run that opened no application forms.

Why a run opens nothing is not always the same, so the next run reacts to the CAUSE the last run recorded:
  handled        most jobs seen were already in your history (the same top results keep coming back)
  no_cards       LinkedIn showed no results for the searches
  rules          the jobs seen were skipped by your own rules (not Easy Apply, not Remote, senior title, years, bad words ...)
  below_cutoff   jobs were scored but none reached your Minimum fit
  open_failures  two or more good jobs were found but their pages or forms would not open (a page problem, not a search problem)

Only SEARCH levers change (which titles, how deep, sort order, how recent). Your own quality and safety rules are never
loosened: Minimum fit, years limit, senior-title skipping, blocked companies, bad words, Remote / United States / Easy Apply.
Where relaxing one of them would help, the next run prints a suggestion and leaves the decision to you.

The record lives in `all excels/run_feedback.json` (local, git-ignored). Pure functions here; hybrid_apply.py does the wiring.
"""
import json, os
from dataclasses import dataclass, field

MAX_LEVEL = 3                    # each empty run adds one lever, up to this; one run that opens a form resets it
MIN_OPEN_FAILURES = 2            # fewer failed pages than this is put down to that one job, not to LinkedIn's layout
MAX_TRIED_TERMS = 40
MAX_RUNS_KEPT = 10
GROUPS = {                       # lever groups, applied cumulatively in the order chosen for the cause
    "titles_depth": "new search titles (not used before) and a deeper look at each search",
    "relevance": "results sorted by relevance instead of newest first",
    "wider_pool": "your config titles as well, and postings from any date",
}
ORDER_DEFAULT = ("titles_depth", "relevance", "wider_pool")
ORDER_BY_CAUSE = {"no_cards": ("wider_pool", "titles_depth", "relevance")}
SKIP_KEYS = ("handled", "not_easy_apply", "not_remote", "title", "blocked_company", "duplicate", "hard_blockers", "bad_words", "company_text")


def empty_feedback():
    return {"streak": 0, "last_cause": "", "last_hint": "", "tried_terms": [], "runs": []}


def load(path):
    try:
        data = json.load(open(path, encoding="utf-8"))
    except Exception:
        return empty_feedback()
    fb = empty_feedback()
    if isinstance(data, dict):
        for k in fb:
            if k in data and isinstance(data[k], type(fb[k])): fb[k] = data[k]
    return fb


def save(path, feedback):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(feedback, open(path, "w", encoding="utf-8"), indent=1)
    except OSError:
        pass


def classify(o):
    """Why this run opened nothing: one of the causes above, or "ok" when at least one form was opened."""
    if o.get("opened", 0) > 0:
        return "ok"
    skips = o.get("skips") or {}
    skipped = sum(int(skips.get(k, 0)) for k in SKIP_KEYS)
    if o.get("good", 0) > 0 and o.get("open_failed", 0) >= MIN_OPEN_FAILURES:      # one job that would not open proves nothing about the page
        return "open_failures"
    if o.get("scored", 0) > 0 and o.get("good", 0) == 0:
        return "below_cutoff"
    if skipped + o.get("scored", 0) == 0 and o.get("searches", 0) > 0:
        return "no_cards"
    if skipped and int(skips.get("handled", 0)) * 2 >= skipped:
        return "handled"
    return "rules"


def hint_for(cause, o):
    """A suggestion for the user (never applied automatically), or ""."""
    if cause == "below_cutoff":
        best, cut = o.get("best_score"), o.get("min_fit")
        return (f"The best fit last time was {best} and your Minimum fit is {cut}. It was not lowered automatically; "
                "lower it in the Run tab if you want weaker matches." if best is not None and cut is not None else
                "Jobs were found but none reached your Minimum fit. Lower it in the Run tab if you want weaker matches.")
    if cause == "open_failures":
        return ("Good jobs were found, but their pages or forms would not open. That points at LinkedIn's page layout, not your search: "
                "use 'Check LinkedIn still works' in the Settings tab.")
    if cause == "no_cards":
        return "LinkedIn showed no results for these searches. Check your location and filters in config/search.py."
    return ""


def counts_as_empty(o):
    """False for runs that say nothing about the search: list-only, daily cap, the user quitting, or the AI failing to score anything."""
    return not (o.get("list_only") or o.get("capped") or o.get("quit") or o.get("ai_failed"))


def record(path, outcome):
    """Store this run's outcome and update the escalation level. Returns the updated feedback."""
    fb = load(path)
    if not counts_as_empty(outcome):
        return fb
    cause = classify(outcome)
    terms = [t for t in outcome.get("terms", []) if isinstance(t, str)]
    if cause == "ok":
        fb["streak"] = 0
        fb["tried_terms"] = terms[-MAX_TRIED_TERMS:]
    elif cause != "open_failures":                        # a page problem is not fixed by searching differently: do not escalate
        fb["streak"] = min(fb["streak"] + 1, MAX_LEVEL)
        seen = {t.lower() for t in fb["tried_terms"]}
        fb["tried_terms"] = (fb["tried_terms"] + [t for t in terms if t.lower() not in seen])[-MAX_TRIED_TERMS:]
    fb["last_cause"] = "" if cause == "ok" else cause
    fb["last_hint"] = hint_for(cause, outcome)
    fb["runs"] = (fb["runs"] + [{k: outcome.get(k) for k in ("time", "scored", "good", "opened", "best_score", "skips", "searches")} | {"cause": cause}])[-MAX_RUNS_KEPT:]
    save(path, fb)
    return fb


@dataclass
class Plan:
    level: int = 0
    cause: str = ""
    per_term: int = 0
    candidates: int = 0
    ai_terms: int = 0
    avoid_terms: list = field(default_factory=list)
    relevance: bool = False
    config_terms: bool = False
    any_time: bool = False
    steps: list = field(default_factory=list)       # plain-English list of what changed
    hint: str = ""


def plan(feedback, per_term, candidates, ai_terms):
    """The approach for the next run, from the stored feedback and the numbers the run was started with."""
    level = min(int(feedback.get("streak", 0)), MAX_LEVEL)
    cause = feedback.get("last_cause", "")
    p = Plan(level=level, cause=cause, per_term=per_term, candidates=candidates, ai_terms=ai_terms, hint=feedback.get("last_hint", ""))
    if level == 0:
        return p
    for group in ORDER_BY_CAUSE.get(cause, ORDER_DEFAULT)[:level]:
        if group == "titles_depth":
            p.avoid_terms = list(feedback.get("tried_terms", []))
            p.per_term = min(20, max(per_term, per_term * 2))
            p.candidates = min(60, max(candidates, int(candidates * 1.5)))
            p.ai_terms = min(16, ai_terms + 4)
        elif group == "relevance":
            p.relevance = True
        elif group == "wider_pool":
            p.config_terms = True
            p.any_time = True
        p.steps.append(GROUPS[group])
    return p


def describe(p):
    """Lines to print at the start of a run that changed its approach (empty when nothing changed)."""
    if not p.steps:
        return [p.hint] if p.hint else []
    why = {"handled": "most jobs it saw were already handled", "no_cards": "LinkedIn showed no results",
           "rules": "the jobs it saw were skipped by your rules", "below_cutoff": "no job reached your Minimum fit"}.get(p.cause, "it opened no forms")
    lines = [f"The last run opened no forms ({why}), so this run takes a different approach (level {p.level} of {MAX_LEVEL}):"]
    lines += [f"   - {s}" for s in p.steps]
    lines.append("   Your own rules (Minimum fit, years, senior titles, Remote, United States, Easy Apply) are unchanged.")
    if p.hint: lines.append("   " + p.hint)
    return lines
