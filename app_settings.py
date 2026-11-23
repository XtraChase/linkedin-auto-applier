"""
User-editable settings in config/app_settings.json (git-ignored). The desktop app edits the same file.
Command-line flags still override these for a single run.
"""
import json, os

from app_paths import home
PATH = os.path.join(home(), "config", "app_settings.json")

DEFAULTS = {
    # --- search and ranking ---
    "min_fit": 30,                 # only apply to jobs the AI scores at or above this
    "candidates": 30,              # jobs to score per run
    "per_term": 8,                 # jobs examined per search title
    "ai_terms": 10,                # search titles the AI chooses from your profile
    "max_years": 7,                # skip postings that require this many years or more
    "allow_senior": False,         # False = skip Senior / Lead / Manager / Director titles
    "max_jobs": 5,                 # application forms to open per run
    "experience_levels": [],       # e.g. ["Entry level", "Associate"]. OFF by default: tested 2026-11-22, LinkedIn's new layout returned identical results with and without f_E
    "blocked_companies": [],       # company names (or parts of names) to never apply to, e.g. ["Crossover", "Staffing"]
    "sort_recent": True,           # newest postings first
    # --- account safety ---
    "persistent_profile": True,    # keep the bot's Chrome signed in between runs (fewer logins than a fresh guest profile)
    "daily_cap": 25,               # stop opening forms after this many submitted applications in one day
    # --- answers ---
    "years_default_fallback": True,    # type the default years when your profile has no figure for a skill
    "letter_original_employers": [],   # names from your template cover letter that must never appear in a letter for another employer
    "cover_letter": "ai",              # "ai" = write one when a form asks for it, "off" = never
    # --- resume ---
    "preferred_resume": "",            # text/regex of the resume file name to select (empty = keep LinkedIn's choice)
    "resume_rules": [],                # [[job-title regex, resume-name regex], ...]  first match wins
}


def load():
    data = dict(DEFAULTS)
    try:
        data.update(json.load(open(PATH, encoding="utf-8")))
    except Exception:
        pass
    return data


def save(data):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    merged = dict(DEFAULTS); merged.update(data)
    json.dump(merged, open(PATH, "w", encoding="utf-8"), indent=1)
    return merged


SETTINGS = load()
