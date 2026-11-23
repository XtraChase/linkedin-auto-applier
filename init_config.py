"""First-run setup: create your private config files from the committed examples.

    .venv\\Scripts\\python.exe init_config.py

Creates (only if missing; never overwrites):
    config/personals.py   your name, phone, address, equal-opportunity answers
    config/questions.py   answers to common application questions
    config/profile.md     the facts the AI is allowed to use
    config/cover_letter_template.md   your own cover letter, which the AI adapts per job
These files are git-ignored so your personal details never get committed.
The packaged .exe calls create_missing() on start, and also restores the config/ package files if the data folder has none.
"""
import os, shutil

import app_paths

RENAMES = {"personals.example.py": "personals.py", "questions.example.py": "questions.py",
           "profile.example.md": "profile.md", "cover_letter_template.example.md": "cover_letter_template.md"}


def create_missing(verbose=False):
    home = app_paths.home()
    config = os.path.join(home, "config")
    os.makedirs(config, exist_ok=True)
    # where the examples (and, for the .exe, the config package files) come from
    src_dir = os.path.join(app_paths.bundle_dir(), "config_examples") if app_paths.frozen() else config
    if not os.path.isdir(src_dir):
        return []
    made = []
    for name in sorted(os.listdir(src_dir)):
        if not os.path.isfile(os.path.join(src_dir, name)): continue
        target = RENAMES.get(name, name)
        if name.endswith(".example.py") or name.endswith(".example.md"):
            if name not in RENAMES: continue
        elif not app_paths.frozen():
            continue                                    # from source, only the personal files are created
        dst = os.path.join(config, target)
        if not os.path.exists(dst):
            shutil.copy2(os.path.join(src_dir, name), dst)
            made.append(target)
            if verbose: print(f"created config/{target}  <- edit this with your own details")
    return made


if __name__ == "__main__":
    made = create_missing(verbose=True)
    if not made: print("Nothing to create: your config files already exist.")
    print("\nNext: edit those files, then put your resume at all resumes/default/resume.pdf")
