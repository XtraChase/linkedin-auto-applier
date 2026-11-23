"""
Build the standalone Windows app:   .venv\\Scripts\\python.exe build_exe.py
Output: dist\\LinkedIn Auto Applier\\LinkedIn Auto Applier.exe  (a folder; copy the whole folder to move it)
The exe name matters for the taskbar: Windows caches icons per file path and per app ID, so a new name (and the app ID in
desktop/main_window.py) starts with a clean slate. If you ever see a stale icon after pinning, change both.

What goes in the exe: the code and libraries. What stays OUT, on purpose: your personal data. The exe finds its data
folder like this (see app_paths.py): the first folder at or above the exe that has config\\personals.py, so an exe built
inside this project uses this project's config, history and resume. Elsewhere it creates a fresh config next to itself.
Only a whitelist of safe config files (no personal files) is staged and bundled as the first-run examples.
"""
import os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(ROOT, "build_staging", "config_examples")
SAFE_CONFIG = ["__init__.py", "_overrides.py", "settings.py", "search.py", "secrets.py", "personals.example.py", "questions.example.py",
               "profile.example.md", "cover_letter_template.example.md"]

# scripts the exe runs as workers: PyInstaller only sees them if they are listed as hidden imports
WORKERS = ["cover_letter_pdf", "hybrid_apply", "health_check", "runAiBot", "migrate_secrets", "init_config", "form_filler", "ai_answers", "answer_audit",
           "answer_memory", "app_settings", "app_paths", "secure_store", "li_selectors", "requirements_check"]
SUBMODULES = ["langchain", "langchain_core", "langchain_openai", "langchain_google_genai", "langgraph", "openai", "google.genai", "tiktoken_ext", "keyring.backends", "modules"]
COLLECT_ALL = ["reportlab", "selenium", "undetected_chromedriver", "pyautogui", "pymsgbox", "pyscreeze", "pytweening", "pygetwindow", "tiktoken", "certifi"]


def stage():
    shutil.rmtree(os.path.join(ROOT, "build_staging"), ignore_errors=True)
    os.makedirs(STAGE)
    for name in SAFE_CONFIG:
        src = os.path.join(ROOT, "config", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(STAGE, name))
    secrets = open(os.path.join(STAGE, "secrets.py"), encoding="utf-8").read()
    for bad in ("sk-", "AIza"):                       # belt and braces: never bundle something that looks like a key
        assert bad not in secrets, "config/secrets.py looks like it contains a key"


def main():
    stage()
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "LinkedIn Auto Applier",
           "--exclude-module", "config", "--add-data", f"{STAGE}{os.pathsep}config_examples",
           "--add-data", f"{os.path.join(ROOT, 'assets')}{os.pathsep}assets", "--icon", os.path.join(ROOT, "assets", "LinkedInAutoApplierIcon_multi.ico")]
    for m in WORKERS: cmd += ["--hidden-import", m]
    for m in SUBMODULES: cmd += ["--collect-submodules", m]
    for m in COLLECT_ALL: cmd += ["--collect-all", m]
    cmd += ["--hidden-import", "keyring.backends.Windows", "desktop_app.py"]
    print("Building (this takes several minutes)...")
    rc = subprocess.call(cmd, cwd=ROOT)
    shutil.rmtree(os.path.join(ROOT, "build_staging"), ignore_errors=True)
    if rc == 0:
        print("\nBuilt:", os.path.join(ROOT, "dist", "LinkedIn Auto Applier", "LinkedIn Auto Applier.exe"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
