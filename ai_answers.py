"""
AI answers for Easy Apply questions, grounded in config/profile.md plus the job posting.

Honesty rules baked into the prompt (this is what keeps the answers true):
  * Only facts in config/profile.md may be claimed. Nothing is invented or exaggerated.
  * If the facts don't clearly support an answer, the AI returns null and the form field is
    left blank for you to answer.
  * The job posting is used to decide WHICH of your true strengths to emphasise, never to
    add skills, years, titles or credentials you do not have.
Every AI-written answer is listed again on the Review page so you can check it before submitting.
"""
import os, re
from typing import Optional
from pydantic import BaseModel, Field

from modules.ai.connections import create_ai_client

from app_paths import home
import app_settings
HERE = home()
PROFILE_PATH = os.path.join(HERE, "config", "profile.md")


class AnswerOut(BaseModel):
    answer: Optional[str] = Field(default=None, description="The answer, or null when the applicant facts do not support one")
    reason: str = Field(default="", description="One short sentence: which fact supports the answer, or what is missing")


PROMPT = """You are filling in ONE question of a job application on behalf of the applicant. The employer reads this, so it must be TRUE.

STRICT RULES
1. Use ONLY the applicant facts below. Never invent or exaggerate experience, employers, job titles, degrees, certifications, licenses, tools, numbers or years.
2. If the facts do not clearly support an answer, set answer to null. Not knowing is fine; guessing is not.
3. Yes/No or choice questions: pick an option only if the facts clearly support it, and return the option text EXACTLY as listed. Otherwise null.
4. "How many years" questions: answer with a single whole number only if the facts give or clearly imply it. Related but different skills do not count. Otherwise null.
5. Sensitive or legal questions (disability, veteran status, race, gender, criminal record, security clearance, licenses) -> null unless the facts state the answer.
6. Free-text questions: write {style}. First person, plain and honest. Use the job posting to choose which TRUE strengths to emphasise. No fabricated claims, no filler like "I am passionate".
7. Return answer null for anything you are unsure about.
8. Tool/software list questions ("Do you have experience with Revit, Navisworks, Bluebeam ...?"): the applicant has confirmed that the answer is Yes when the facts show experience with AT LEAST ONE of the listed tools (or an obvious product-family match, e.g. AutoCAD or Civil 3D for "Autodesk"). Answer No only when the facts show none of them. This rule applies only to such tool lists, never to licenses, degrees, clearances or years.

APPLICANT FACTS
{profile}

JOB
Title: {title}
Company: {company}
Job posting (what the employer is looking for):
{description}

About the company:
{about}

QUESTION: {question}
QUESTION TYPE: {qtype}
{options_block}"""


def load_profile():
    try:
        return open(PROFILE_PATH, encoding="utf-8").read()
    except FileNotFoundError:
        return ""


class AIAnswerer:
    def __init__(self, job=None, log=print):
        self.job = job or {}
        self.log = log
        self.profile = load_profile()
        self.client = create_ai_client()
        self.ok = bool(self.client) and bool(self.profile.strip())
        if self.client and not self.profile.strip():
            self.log("   (AI is on but config/profile.md is empty, so AI answers are disabled)")
        self.cache = {}

    def set_job(self, job):
        self.job = job or {}

    def answer(self, it):
        """Return an answer string for question item `it`, or None when the facts don't support one."""
        if not self.ok:
            return None
        label = it["label"].strip()
        kind = it["kind"]
        if kind == "radio": options = [o["text"] for o in it["options"]]
        elif kind == "select": options = [o for o in it["options"] if o.strip()]
        else: options = None
        key = (self.job.get("id"), label, tuple(options or []))
        if key in self.cache: return self.cache[key]

        maxlen = int(it.get("maxlength") or 0)
        if kind == "textarea": style = "2 to 5 honest sentences (under 900 characters)"
        else: style = "ONE short line (under 120 characters)"
        if kind in ("text",) and maxlen: style = f"a very short answer of at most {maxlen} characters"
        options_block = ("OPTIONS (return one exactly):\n" + "\n".join(f"- {o}" for o in options)) if options else "(free answer)"
        prompt = PROMPT.format(
            style=style, profile=self.profile.strip(),
            title=self.job.get("title", ""), company=self.job.get("company", ""),
            description=(self.job.get("description") or "")[:5000], about=(self.job.get("about") or "")[:1500],
            question=label, qtype=kind if not options else f"{kind} (choose one)", options_block=options_block)
        out = None
        try:
            structured = self.client.model.with_structured_output(AnswerOut)
            res = structured.invoke(prompt)
            out = (res.answer or "").strip() or None
            reason = res.reason
        except Exception as e:
            self.log(f"   (AI call failed for \"{label[:60]}\": {type(e).__name__})")
            self.cache[key] = None
            return None
        if out and options:
            low = [o.lower().strip() for o in options]
            if out.lower().strip() in low: out = options[low.index(out.lower().strip())]
            else: out = None                        # not one of the options -> don't guess
        if out and re.search(r"year", label, re.I) and kind in ("text", "textarea"):
            m = re.search(r"\d+(\.\d+)?", out)
            out = m.group(0) if m else None
        if out and out.lower() in ("null", "none", "n/a", "unknown"): out = None
        if out and maxlen and kind != "textarea": out = out[:maxlen]
        self.log(f"   AI: {label[:70]!r} -> {out!r}  ({reason[:90]})")
        self.cache[key] = out
        return out


# ---------------------------------------------------------------------------------------------
# Job search help: suggest search titles, and score how well a posting fits you
# ---------------------------------------------------------------------------------------------
class TermsOut(BaseModel):
    terms: list[str] = Field(default_factory=list, description="LinkedIn job-title search phrases")


class FitOut(BaseModel):
    role_match: int = Field(description="0-100: how well the job title and duties match the applicant's target roles")
    skills_match: int = Field(description="0-100: share of the software and skills the posting asks for that the applicant really has")
    experience_fit: int = Field(description="0-100: how well the required years, seniority and qualifications match the applicant")
    reason: str = Field(default="", description="One sentence: the main reason for the ratings")
    gaps: str = Field(default="", description="Requirements the applicant does not appear to meet, or empty")


SCORE_VERSION = 2          # bump when the scoring method changes, so cached scores from older versions are ignored


TERMS_PROMPT = """From the applicant facts below, list up to {n} job-title search phrases to type into LinkedIn Jobs.
They must be roles the applicant could realistically win, remote in the United States, matching the target roles and real skills.
FOCUS: about 70 to 80 percent of the phrases must be DRAFTING and CAD roles (for example CAD Drafter, AutoCAD Drafter, Architectural Drafter,
Revit Drafter, Drafting Technician, Civil Drafter, Mechanical Drafter, CAD Technician, CAD Operator). Use the rest for Revit / BIM modeling and 3D modeling.
Prefer entry-level and junior friendly titles; the applicant is early in a drafting career. Never include Senior, Lead, Manager or Director.
Short phrases (1 to 4 words), no duplicates. Do not repeat these existing phrases: {existing}

APPLICANT FACTS
{profile}"""

FIT_PROMPT = """Rate how well this job fits the applicant with THREE separate 0-100 ratings. Use ONLY the applicant facts. Be realistic, not flattering.
role_match: 90+ the title and duties are exactly the applicant's target roles; 60-80 close; 30-50 related field; under 30 a different field.
skills_match: the share of software and skills the posting asks for that the applicant really has (their facts list them). 100 = all, 50 = about half, 0 = none.
experience_fit: 90+ the stated years and qualifications are within what the applicant has; 60-80 one small gap (about 1 year short);
40-60 a clear gap (2 to 3 years short, or a degree in a field they lack); under 30 a hard gap (licenses, clearances, many years in a trade not in the facts).
The job must be remote and in the United States; if the posting is not, give all three ratings 0.

APPLICANT FACTS
{profile}

JOB: {title} at {company} ({location})
POSTING:
{description}"""


def _suggest_terms(self, n=8, existing=()):
    if not self.ok: return []
    try:
        res = self.client.model.with_structured_output(TermsOut).invoke(
            TERMS_PROMPT.format(n=n, existing=", ".join(existing) or "none", profile=self.profile.strip()))
        seen = {t.lower() for t in existing}
        out = []
        for t in res.terms:
            t = re.sub(r"\s+", " ", t).strip()
            if t and t.lower() not in seen and len(t) <= 60:
                seen.add(t.lower()); out.append(t)
        return out[:n]
    except Exception as e:
        self.log(f"   (AI could not suggest search terms: {type(e).__name__})")
        return []


def _score_job(self, job):
    """Return (score 0-100, one-line reason). Score -1 when the AI is unavailable."""
    if not self.ok: return -1, "AI unavailable"
    prompt = FIT_PROMPT.format(
        profile=self.profile.strip(), title=job.get("title", ""), company=job.get("company", ""),
        location=job.get("location", ""), description=(job.get("description") or "")[:6000])
    last = None
    for deterministic in (True, False):          # temperature 0 for steadier scores; fall back if the model refuses it
        try:
            model = self.client.model.bind(temperature=0) if deterministic else self.client.model
            res = model.with_structured_output(FitOut).invoke(prompt)
            clip = lambda v: max(0, min(100, int(v)))
            score = round(0.30 * clip(res.role_match) + 0.35 * clip(res.skills_match) + 0.35 * clip(res.experience_fit))
            reason = res.reason.strip()
            if res.gaps.strip(): reason += f" | gaps: {res.gaps.strip()}"
            reason += f" [role {clip(res.role_match)}, skills {clip(res.skills_match)}, experience {clip(res.experience_fit)}]"
            return score, reason
        except Exception as e:
            last = e
    return -1, f"scoring failed: {type(last).__name__}"


COVER_PROMPT = """Adapt the applicant's OWN cover letter (below) for a different job. Keep their voice, paragraph structure and wording as much as possible.
Change only what this job needs:
  - Replace the company name and role everywhere. Everything specific to the ORIGINAL employer (its office, city, mission, local community, position title) must be replaced or removed.
  - Re-order or lightly trim the experience paragraphs so the strengths that match THIS posting come first.
  - The company-specific paragraph may use ONLY facts stated in the posting or the company description below. If they give nothing specific, replace it with one honest, general sentence about why the role fits.
  - Keep the contact line and the sign-off.
RULES: use ONLY the applicant facts and their original letter. Never invent or exaggerate experience, employers, titles, degrees, tools, numbers or years.
No placeholders or brackets. Never mention being an AI. {length_rule}
Plain text only: no date, no address block, no markdown.

APPLICANT FACTS
{profile}

APPLICANT'S ORIGINAL LETTER
{template}

JOB: {title} at {company} ({location})
POSTING:
{description}

ABOUT THE COMPANY:
{about}"""

GENERIC_COVER_PROMPT = """Write a short cover letter for this job application, 150 to 220 words, plain text.
RULES: use ONLY the applicant facts below. Never invent or exaggerate experience, employers, titles, degrees, tools, numbers or years.
Choose the applicant's TRUE strengths that best match what the posting asks for, and say honestly that the applicant is early in a drafting career if the facts show that.
Start with "Dear Hiring Team," and end with the applicant's first name. No placeholders, no brackets, no "I am passionate", never mention being an AI. {length_rule}

APPLICANT FACTS
{profile}

JOB: {title} at {company}
POSTING:
{description}"""

TEMPLATE_PATH = os.path.join(HERE, "config", "cover_letter_template.md")


def _cover_letter(self, maxlen=0):
    """A cover letter for the current job adapted from config/cover_letter_template.md (your own letter), or None.
    Also saved to all excels/cover_letters/ so you can read exactly what was sent."""
    if not self.ok: return None
    try:
        template = ""
        try:
            template = open(TEMPLATE_PATH, encoding="utf-8").read().strip()
        except FileNotFoundError:
            pass
        length_rule = f"The letter must be at most {maxlen} characters." if maxlen else ""
        if template:
            prompt = COVER_PROMPT.format(profile=self.profile.strip(), template=template, title=self.job.get("title", ""),
                                         company=self.job.get("company", ""), location=self.job.get("location", ""),
                                         description=(self.job.get("description") or "")[:5000], about=(self.job.get("about") or "")[:1500],
                                         length_rule=length_rule)
        else:
            prompt = GENERIC_COVER_PROMPT.format(profile=self.profile.strip(), title=self.job.get("title", ""),
                                                 company=self.job.get("company", ""),
                                                 description=(self.job.get("description") or "")[:5000], length_rule=length_rule)
        res = self.client.model.invoke(prompt)
        text = (getattr(res, "content", "") or "")
        if isinstance(text, list): text = " ".join(str(x) for x in text)
        text = text.strip()
        if not text or re.search(r"\[[^\]]{2,40}\]", text): return None            # leftover placeholder like [Your Name]
        posting = (self.job.get("company", "") + " " + (self.job.get("description") or "")).lower()
        for old_name in app_settings.load().get("letter_original_employers", []):
            if old_name and old_name.lower() in text.lower() and old_name.lower() not in posting:
                return None                                                         # the employer of the template letter leaked into a different job's letter
        if maxlen and len(text) > maxlen: text = text[:maxlen].rsplit(" ", 1)[0]
        folder = os.path.join(HERE, "all excels", "cover_letters")
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, f"{self.job.get('id', 'job')}.txt"), "w", encoding="utf-8").write(text)
        return text
    except Exception as e:
        self.log(f"   (AI could not write a cover letter: {type(e).__name__})")
        return None


AIAnswerer.suggest_terms = _suggest_terms
AIAnswerer.score_job = _score_job
AIAnswerer.cover_letter = _cover_letter
