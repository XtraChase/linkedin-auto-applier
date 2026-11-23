"""Quick checks before a run, so a new user hears "you have not saved an AI key yet" before Chrome opens, not halfway through."""
import glob, os

import secure_store
from desktop import data

RESUME_EXT = (".pdf", ".doc", ".docx")


def has_resume(root):
    """True when any resume file sits anywhere under <root>/all resumes/."""
    for dirpath, _dirs, files in os.walk(os.path.join(root, "all resumes")):
        if any(f.lower().endswith(RESUME_EXT) for f in files):
            return True
    return False


def check(no_ai=False, root=None, profile_path=None, key_present=None):
    """Problems worth knowing about before Start, as a list of plain-English sentences (empty list = all good)."""
    root = root or data.ROOT
    profile_path = profile_path or data.PROFILE
    problems = []
    if not no_ai:
        key = secure_store.get("llm_api_key") if key_present is None else key_present
        if not key:
            problems.append("No AI API key is saved (Settings tab, Secrets). Without it the bot cannot rank jobs or write answers.")
    try:
        facts = open(profile_path, encoding="utf-8").read()
    except OSError:
        facts = ""
    if not facts.strip() or "First Last" in facts:
        problems.append("Your facts (Profile tab) are empty or still the template. The AI may only use what is written there.")
    if not has_resume(root):
        problems.append("No resume found in the 'all resumes' folder (for example all resumes\\default\\resume.pdf). Forms that need one will be left for you.")
    return problems
