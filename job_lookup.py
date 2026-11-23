"""Find what the bot already knows about a job (from the score cache and the history) so it can be applied to by id."""
import csv


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
