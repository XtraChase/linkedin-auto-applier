"""Data access for the desktop app. Pure Python (no Qt), so it can be tested without a window."""
import csv, json, os, re, time

from app_paths import home
ROOT = home()
CONFIG = os.path.join(ROOT, "config")
EXCEL = os.path.join(ROOT, "all excels")
HISTORY = os.path.join(EXCEL, "hybrid_history.csv")
CACHE = os.path.join(EXCEL, "score_cache.json")
ANSWERS_LOG = os.path.join(EXCEL, "answers_log.jsonl")
MEMORY = os.path.join(CONFIG, "answers.json")
PROFILE = os.path.join(CONFIG, "profile.md")
COVER = os.path.join(CONFIG, "cover_letter_template.md")


def _fit_from_status(status):
    m = re.search(r"fit (\d+)", status or "")
    return int(m.group(1)) if m else None


def load_jobs():
    """All jobs the bot has seen, best fit first: [{id, score, title, company, status, reason, link, time}]."""
    jobs = {}
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        cache = {}
    for jid, c in cache.items():
        jobs[jid] = {"id": jid, "score": c.get("score"), "title": c.get("title", ""), "company": c.get("company", ""),
                     "status": "scored", "reason": c.get("reason", ""), "time": c.get("ts", 0)}
    try:
        with open(HISTORY, encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 6 or row[0] == "job_id": continue
                jid, title, company, _loc, _link, status = row[:6]
                j = jobs.setdefault(jid, {"id": jid, "score": None, "reason": "", "time": 0})
                j.update(title=title or j.get("title", ""), company=company or j.get("company", ""), status=status,
                         time=row[6] if len(row) > 6 else "")
                s = _fit_from_status(status)
                if s is not None: j["score"] = s
    except FileNotFoundError:
        pass
    for j in jobs.values():
        j["link"] = "https://www.linkedin.com/jobs/view/" + j["id"] + "/"
    return sorted(jobs.values(), key=lambda j: -(j["score"] if j["score"] is not None else -1))


def load_memory():
    """Remembered answers: [{question, answer, kind, saved}]."""
    try:
        data = json.load(open(MEMORY, encoding="utf-8"))
    except Exception:
        return []
    return [{"key": k, "question": v.get("question", k), "answer": v.get("answer", ""), "kind": v.get("kind", ""),
             "saved": v.get("saved", "")} for k, v in data.items()]


def save_memory(rows):
    from answer_memory import normalize
    data = {}
    for r in rows:
        q, a = (r.get("question") or "").strip(), (r.get("answer") or "").strip()
        if not q or not a: continue
        data[normalize(q)] = {"question": q, "answer": a, "kind": r.get("kind") or "text",
                              "source": "you", "saved": r.get("saved") or time.strftime("%Y-%m-%d %H:%M")}
    os.makedirs(CONFIG, exist_ok=True)
    json.dump(data, open(MEMORY, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def recent_applications(limit=30):
    """Newest first: [{time, title, company, result, answers:[{q,a,source,flags}]}] from the audit log."""
    out = []
    try:
        with open(ANSWERS_LOG, encoding="utf-8") as f:
            for line in f:
                try: out.append(json.loads(line))
                except ValueError: pass
    except FileNotFoundError:
        pass
    return out[::-1][:limit]


CURRENT_JOB = os.path.join(EXCEL, "current_job.json")


def read_current_job():
    """The job the bot is applying to right now (written by hybrid_apply), or None."""
    try:
        return json.load(open(CURRENT_JOB, encoding="utf-8"))
    except Exception:
        return None


def set_history_status(job_id, status, title="", company=""):
    """Change a job's outcome in the history (e.g. mark it as submitted). Adds a row if the job is not in the history yet."""
    os.makedirs(EXCEL, exist_ok=True)
    rows, found = [], False
    try:
        with open(HISTORY, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        pass
    if not rows:
        rows = [["job_id", "title", "company", "location", "link", "status", "time"]]
    for row in rows[1:]:
        if row and row[0] == job_id:
            while len(row) < 7: row.append("")
            row[5] = status; row[6] = time.strftime("%Y-%m-%dT%H:%M:%S"); found = True
    if not found:
        rows.append([job_id, title, company, "", "https://www.linkedin.com/jobs/view/" + job_id, status, time.strftime("%Y-%m-%dT%H:%M:%S")])
    with open(HISTORY, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def read_text(path):
    try:
        return open(path, encoding="utf-8").read()
    except FileNotFoundError:
        example = path.replace(".md", ".example.md")
        return open(example, encoding="utf-8").read() if os.path.exists(example) else ""


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)
