"""
Rule-based blockers: drop jobs you clearly cannot get BEFORE spending an AI call or a page load on them.

  * title_blocker(title): senior / lead / manager / director style titles.
  * hard_blockers(text):  licenses (PE, registered architect), clearances, and very high required years.

These are cheap heuristics. They only ever skip a job; they never claim anything about you.
"""
import re

TITLE_EXCLUDE = re.compile(r"\b(senior|sr\.?|lead|principal|director|manager|head of|vp|vice president|chief|staff|supervisor)\b", re.I)

LICENSE_PATTERNS = [
    (r"\b(pe|p\.e\.)\s+(license|licence|licensed|certification)|professional engineer(ing)?\s+(license|licence|licensed)|licensed professional engineer|\bpe license\b",
     "requires a PE license"),
    (r"licensed architect|registered architect|architect(ural)? licen[cs]e|\bra\s+licen[cs]e",
     "requires an architect license"),
    (r"(active|current|valid)\s+(dod\s+)?(secret|top secret|ts/sci)\s+(security\s+)?clearance|security clearance\s+(is\s+)?required|must\s+(hold|have|possess|obtain).{0,40}clearance|ts/sci",
     "requires a security clearance"),
]

YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years|yrs)\b", re.I)
NEEDS_CONTEXT = re.compile(r"required|requirement|minimum|at least|must|qualification|you have|you bring|candidate|applicant|experience (with|in|using|as)|proven", re.I)
COMPANY_BRAG = re.compile(r"our company|we have|we've|for over|founded|since (19|20)\d\d|history|in business|serving|established", re.I)
PREFERRED = re.compile(r"prefer|nice to have|a plus|bonus|ideal", re.I)


def title_blocker(title):
    m = TITLE_EXCLUDE.search(title or "")
    return f'title says "{m.group(0)}"' if m else None


def hard_blockers(text, max_years=7):
    """Reasons to skip this posting; empty list when nothing blocks it."""
    text = text or ""
    reasons = []
    low = text.lower()
    for pat, why in LICENSE_PATTERNS:
        if re.search(pat, low) and why not in reasons:
            reasons.append(why)
    worst = 0
    for sentence in re.split(r"(?<=[.!?\n])\s+|\n", text):
        if not YEARS_RE.search(sentence) or COMPANY_BRAG.search(sentence) or not NEEDS_CONTEXT.search(sentence):
            continue
        if PREFERRED.search(sentence):
            continue
        for m in YEARS_RE.finditer(sentence):
            n = int(m.group(1))
            if n < 30: worst = max(worst, n)
    if worst >= max_years:
        reasons.append(f"asks for {worst}+ years of experience")
    return reasons
