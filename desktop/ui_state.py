"""Remember window size and last-used choices between launches. One small JSON file in the app's own config folder (git-ignored)."""
import json, os

from desktop import data

PATH = os.path.join(data.CONFIG, "ui_state.json")


def load():
    try:
        d = json.load(open(PATH, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save(state):
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        json.dump(state, open(PATH, "w", encoding="utf-8"), indent=1)
    except OSError:
        pass
