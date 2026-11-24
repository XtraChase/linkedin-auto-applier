"""Find what the bot already knows about a job (from the score cache and the history) so it can be applied to by id,
and turn a pasted LinkedIn link into a job id."""
import csv
import re
from urllib.parse import parse_qs, urlparse


def parse_job_link(text):
    """The LinkedIn job id in a pasted link (or a bare id), as a string, or "" when it is not one.

    Accepts linkedin.com/jobs/view/<id>/ (also with a title slug before the id, or the /comm/ prefix), search and collection
    links that carry ?currentJobId=<id>, and a plain number of 8 or more digits. Other websites are refused."""
    text = (text or "").strip().strip("<>\"'")
    if not text:
        return ""
    if re.fullmatch(r"\d{8,}", text):
        return text
    if "://" not in text:
        text = "https://" + text
    try:
        u = urlparse(text)
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return ""
    q = parse_qs(u.query)
    for key in ("currentJobId", "jobId"):
        if q.get(key) and re.fullmatch(r"\d{8,}", q[key][0]):
            return q[key][0]
    m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{8,})(?:[/?#]|$)", u.path)
    return m.group(1) if m else ""


def history_row(job_id, path):
    """The newest history row for this job as a dict, or {}."""
    found = {}
    try:
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("job_id") == job_id:
                    found = row
    except FileNotFoundError:
        pass
    return found


def build_job(job_id, cache_entry=None, history=None):
    """A job dict for hybrid_apply from whatever is known. `term` is the search words used to open the job's page."""
    c, h = cache_entry or {}, history or {}
    title = c.get("title") or h.get("title") or ""
    return {"id": job_id, "title": title, "company": c.get("company") or h.get("company") or "",
            "location": c.get("location") or h.get("location") or "", "score": c.get("score"), "reason": c.get("reason", ""),
            "description": c.get("description", ""), "about": c.get("about", ""), "term": title or "CAD Drafter"}


def parse_job_meta(info):
    """Title, company and location of the open job page from what JOB_META_JS read: {ld, og, doc} (any may be empty).
    The page's structured data is preferred; the page title ("Company hiring Title in Place | LinkedIn") is the fallback."""
    info = info or {}
    ld = info.get("ld") or {}
    title, company, location = (ld.get("title") or "").strip(), (ld.get("company") or "").strip(), (ld.get("location") or "").strip()
    if not (title and company):
        for raw in (info.get("og"), info.get("doc")):
            raw = re.sub(r"\s*\|\s*LinkedIn\s*$", "", (raw or "").strip())
            m = re.match(r"^(?P<co>.+?) (?:is )?hiring (?P<t>.+?)(?: in (?P<loc>.+))?$", raw)
            if m:
                title, company = title or m.group("t").strip(), company or m.group("co").strip()
                location = location or (m.group("loc") or "").strip()
                break
            parts = [p.strip() for p in raw.split(" | ") if p.strip()]
            if len(parts) >= 2:
                title, company = title or parts[0], company or parts[1]
                break
    return {"title": title, "company": company, "location": location}
