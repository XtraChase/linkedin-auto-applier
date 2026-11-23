"""
Make the README screenshots from FICTIONAL demo data (no real person, jobs or keys).

    .venv\Scripts\python.exe tools\make_screenshots.py

It builds a throw-away data folder (LAA_HOME) with an invented applicant, invented companies and made-up answers, opens the
real desktop window on it, and saves PNGs to docs/screenshots/. Your own config, history and keys are never read.
"""
import json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("SHOT_OUT") or os.path.join(HERE, "docs", "screenshots")      # SHOT_OUT / SHOT_SIZE=900x640: for layout checks
home = tempfile.mkdtemp(prefix="laa_demo_")
os.environ["LAA_HOME"] = home
sys.path.insert(0, HERE)
for d in ("config", "all excels"):
    os.makedirs(os.path.join(home, d), exist_ok=True)

JOBS = [  # id, title, company, fit, status, why
    ("4100000001", "CAD Drafter (Remote)", "Northwind Drafting Co", 88, "stopped at review (closed, not submitted)", "Strong match: CAD drafting, AutoCAD and Revit experience, remote US."),
    ("4100000002", "Revit BIM Technician", "Example Engineering Group", 82, "applied (fit 82)", "Revit and BIM modeling match your facts; entry-level friendly."),
    ("4100000003", "Architectural Drafter", "Sample Design Studio", 76, "scored", "Drafting and construction documents match; no PE license required."),
    ("4100000004", "3D Technical Artist", "Demo Interactive", 71, "scored", "3D modeling matches (8 years); some engine tools not listed in your facts."),
    ("4100000005", "Mechanical Drafter", "Acme Fabrication", 64, "scored", "Drafting matches; SolidWorks not in your facts."),
    ("4100000006", "Civil Design Technician", "Placeholder Civil Inc", 52, "scored", "Partial match: CAD yes, civil site design not in your facts."),
    ("4100000007", "Senior Structural Designer", "Fictional Structures LLC", 28, "skipped: senior title", "Senior title and 8+ years required."),
]
cache = {j[0]: {"score": j[3], "title": j[1], "company": j[2], "reason": j[5], "ts": time.time()} for j in JOBS}
json.dump(cache, open(os.path.join(home, "all excels", "score_cache.json"), "w"), indent=1)
with open(os.path.join(home, "all excels", "hybrid_history.csv"), "w", encoding="utf-8", newline="") as f:
    f.write("job_id,title,company,location,link,status,time\n")
    for j in JOBS:
        if j[4] != "scored":
            f.write(f"{j[0]},{j[1]},{j[2]},Remote,x,{j[4]},2026-01-15T10:00:00\n")

log = [
    {"time": "2026-01-15T10:05:00", "title": "Revit BIM Technician", "company": "Example Engineering Group", "result": "applied (fit 82)", "answers": [
        {"q": "Years of experience with Revit", "a": "3", "source": "default", "flags": ["used the default years figure"]},
        {"q": "Are you legally authorized to work in the United States?", "a": "Yes", "source": "config", "flags": []},
        {"q": "Do you now or in the future require sponsorship?", "a": "No", "source": "config", "flags": []},
        {"q": "Why are you interested in this role?", "a": "I enjoy turning design intent into clear, accurate models and drawings.", "source": "ai", "flags": ["free-text answer written by the AI"]}]},
]
with open(os.path.join(home, "all excels", "answers_log.jsonl"), "w", encoding="utf-8") as f:
    for r in log: f.write(json.dumps(r) + "\n")

open(os.path.join(home, "config", "profile.md"), "w", encoding="utf-8").write("""# Applicant facts (the AI may use ONLY what is written here)

## Basics
- Name: Alex Example
- Location: Anytown, USA
- Work authorization: legally authorized to work in the United States, no sponsorship needed
- Prefers: remote roles in the United States

## Target roles
Mostly remote drafting and CAD roles; also open to Revit / BIM modeling.

## Experience (most recent first)
- CAD Drafter, Example Co, 2023 - present. Produced construction documents and details in AutoCAD and Revit.

## Years of experience (stated by me)
- 3D modeling: about 8 years.
- Drafting: about 3 years.

## Software and skills
AutoCAD, Revit, Blender, Microsoft Office.

## Not provided (leave these for me to answer)
Professional licenses, security clearances.
""")
open(os.path.join(home, "config", "cover_letter_template.md"), "w", encoding="utf-8").write("""Dear Hiring Manager,

I am excited to apply for the [role] position at [company]. For the past three years I have produced clear, accurate drawings
and models in AutoCAD and Revit, and I take pride in details that are easy to build from.

Thank you for your time and consideration.

Sincerely,
Alex Example
""")
open(os.path.join(home, "config", "personals.py"), "w").write("first_name = 'Alex'\n")
mem = {"Do you have experience with AutoCAD?": ("Yes", "radio"), "What is your desired salary?": ("60000", "text"), "Are you comfortable working remotely?": ("Yes", "radio")}

from PySide6.QtWidgets import QApplication
app = QApplication([])
from desktop import theme
theme.apply(app)                       # the same look as the real app
from desktop import data
data.save_memory([{"question": q, "answer": a, "kind": k} for q, (a, k) in mem.items()])
import secure_store
secure_store.get = lambda name: "demo" if name == "llm_api_key" else ""         # show "stored" for the AI key only, never read the real vault
import app_settings
app_settings.save({})
from desktop.main_window import MainWindow
SIZE = [int(x) for x in os.environ.get("SHOT_SIZE", "1180x760").split("x")]
w = MainWindow(); w.resize(*SIZE); w.show(); app.processEvents()
runner, run = w.runner, w.run_tab

def backdrop(size):
    """A made-up blurred 'desktop' for the translucent window to sit on (the real app shows your own desktop through it)."""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = (x / W + y / H) / 2
            px[x, y] = (int(20 + 70 * t), int(55 + 15 * t), int(120 + 60 * t))
    d = ImageDraw.Draw(img)
    for cx, cy, r, col in ((0.12, 0.15, 0.35, (40, 190, 230)), (0.85, 0.20, 0.30, (230, 120, 190)), (0.70, 0.90, 0.40, (140, 90, 255)), (0.15, 0.85, 0.30, (60, 150, 255))):
        d.ellipse([(cx - r) * W, (cy - r) * H, (cx + r) * W, (cy + r) * H], fill=col)
    return img.filter(ImageFilter.GaussianBlur(min(W, H) * 0.12))


def shot(name):
    app.processEvents(); time.sleep(0.4); app.processEvents()
    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    path = os.path.join(OUT, name + ".png")
    w.grab().save(path)
    top = Image.open(path).convert("RGBA")
    base = backdrop(top.size).convert("RGBA")
    base.alpha_composite(top)
    base.convert("RGB").save(path, optimize=True); print("saved", name)

# Run tab: a finished-looking session waiting at the Submit page
for line in ["Login successful!", "=== Choosing search titles ===", "   CAD Drafter | Revit BIM Technician | Architectural Drafter | 3D Technical Artist",
             "=== Searching LinkedIn (remote, United States, Easy Apply, past month) ===", "   scanned 30 jobs, scored 22, 9 at or above your minimum fit",
             "RANKED", "  1. [88] CAD Drafter (Remote) | Northwind Drafting Co", "  2. [82] Revit BIM Technician | Example Engineering Group",
             ">>> Applying to #1: [88] CAD Drafter (Remote) | Northwind Drafting Co", "   job-link: https://www.linkedin.com/jobs/view/4100000001/",
             "   Form open: filling in the application", "   page 1: contact details filled", "   page 2: resume chosen", "   page 3: 4 questions answered",
             "SUBMIT PAGE reached: read the answers below, then submit it yourself in the Chrome window"]:
    runner.line.emit(line)
runner.prompt.emit("   Did you submit it? y = yes, Enter = no, q = quit: ")
run.auto_submit.setChecked(False)
w.tabs.setCurrentWidget(run); shot("run")
w.tabs.setCurrentWidget(w.jobs_tab); w.jobs_tab.refresh(); shot("jobs")
w.tabs.setCurrentWidget(w.answers_tab); w.answers_tab.refresh(); shot("answers")
w.tabs.setCurrentWidget(w.profile_tab); shot("profile")
w.tabs.setCurrentWidget(w.settings_tab); shot("settings")
w.close()
