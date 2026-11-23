"""
One-time move of secrets out of plain text.

Reads user_config.json (written by the old control panel), stores the AI key and LinkedIn login in
Windows Credential Manager, then blanks those values in the file. Secret values are never printed.

    .venv\\Scripts\\python.exe migrate_secrets.py
"""
import json, os

import secure_store

from app_paths import home
PATH = os.path.join(home(), "user_config.json")
MAP = {"llm_api_key": "llm_api_key", "username": "linkedin_username", "password": "linkedin_password"}


def main():
    if not os.path.exists(PATH):
        print("No user_config.json found; nothing to move."); return
    data = json.load(open(PATH, encoding="utf-8"))
    sec = data.get("secrets", {})
    moved = []
    for key, store_name in MAP.items():
        val = (sec.get(key) or "").strip()
        if val and val not in ("not-needed", "username@example.com", "example_password"):
            secure_store.set(store_name, val)
            if secure_store.get(store_name) != val:
                print(f"Could not verify {store_name} in the vault; leaving user_config.json untouched."); return
            sec[key] = ""
            moved.append(store_name)
    data["secrets"] = sec
    json.dump(data, open(PATH, "w", encoding="utf-8"), indent=2)
    print("Moved to Windows Credential Manager:", ", ".join(moved) if moved else "(nothing to move)")


if __name__ == "__main__":
    main()
