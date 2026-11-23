"""
Audit trail and risk flags for every answer typed into an application.

Sources:  config | memory | ai | default-years | kept (LinkedIn pre-filled) | you (typed by you)
Every application's answers are appended to all excels/answers_log.jsonl so you can look back at
exactly what was sent under your name. Risky answers are flagged on the Submit page.
"""
import json, os, re, time

from app_paths import home
HERE = home()
LOG_PATH = os.path.join(HERE, "all excels", "answers_log.jsonl")

# (pattern on the question, reason). A flag only matters when the answer came from AI, a default, or LinkedIn's memory.
RISK_RULES = [
    (r"\byears?\b|how many years", "claims years of experience"),
    (r"experience|proficien|skilled|expert|familiar|knowledge", "claims experience or skill"),
    (r"degree|diploma|bachelor|master|certif|licen[cs]e|clearance|coursework|education", "education / credential claim"),
    (r"authori[sz]ed|sponsor|citizen|visa|eligible to work", "legal work status"),
    (r"salary|compensation|\bpay\b|\bctc\b|rate", "pay"),
    (r"relocat|commute|travel|on-?site|start date|notice|available|availability", "availability / logistics"),
    (r"background check|drug|felony|convict|criminal", "background / legal"),
    (r"disab|veteran|gender|\brace\b|ethnic", "equal-opportunity question"),
]


def risk_flags(label, answer, source):
    """Reasons this answer deserves a human look. Config answers are yours already, so they are not flagged."""
    flags = []
    if source in ("config", "you"):
        return flags
    if source == "default-years":
        flags.append("default years from your config; your profile has no figure for this skill")
    L = (label or "").lower()
    for pat, why in RISK_RULES:
        if re.search(pat, L) and why not in flags:
            flags.append(why)
    # a Yes to a list of tools/software on partial evidence
    if source == "ai" and (answer or "").strip().lower() == "yes" and L.count(",") >= 2 and re.search(r"experience|proficien|software|tools?", L):
        flags.append("Yes to a list of tools: you may not have all of them")
    if source == "kept":
        flags.append("pre-filled by LinkedIn from an earlier application")
    return flags


# Flags serious enough to stop an AUTOMATIC submit (an answer the AI wrote or a default was guessed for these)
SERIOUS_FLAGS = ("default years", "education / credential claim", "legal work status", "background / legal",
                 "equal-opportunity question", "Yes to a list of tools")


def review_reasons(answers, unanswered=()):
    """Why an application should NOT be submitted automatically (empty list = fine to submit).
    Answers from your config, your saved answers or typed by you never count; AI answers and guessed defaults do."""
    reasons = []
    if unanswered:
        reasons.append(f"{len(unanswered)} question(s) left blank: " + "; ".join(u[:50] for u in list(unanswered)[:3]))
    for a in answers:
        if a["source"] in ("config", "you", "memory"): continue
        for f in a["flags"]:
            if f.startswith(SERIOUS_FLAGS):
                reasons.append(f'"{a["q"][:60]}" ({f})')
    return reasons


def summarize(answers, log=print):
    """Print the Submit-page review: flagged answers first, then the rest by source."""
    if not answers: return
    flagged = [a for a in answers if a["flags"]]
    log("   ============ REVIEW BEFORE YOU SUBMIT ============")
    if flagged:
        log("   !! Needs your eyes:")
        for a in flagged:
            log(f"      Q: {a['q'][:110]}\n      A: {a['a'][:240]}   [{a['source']}; {'; '.join(a['flags'])}]")
    for src, title in (("ai", "Written by the AI"), ("memory", "From your remembered answers"), ("you", "Typed by you"),
                       ("config", "From your config"), ("kept", "Kept from LinkedIn")):
        rows = [a for a in answers if a["source"] == src and not a["flags"]]
        if not rows: continue
        log(f"   {title}:")
        for a in rows:
            log(f"      - {a['q'][:90]}  ->  {a['a'][:120]}")
    log("   ==================================================")


def write_log(job, answers, result=None):
    """Append one line per application to all excels/answers_log.jsonl."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "job_id": (job or {}).get("id"),
                                "title": (job or {}).get("title"), "company": (job or {}).get("company"),
                                "result": result, "answers": answers}, ensure_ascii=False) + "\n")
    except Exception:
        pass
