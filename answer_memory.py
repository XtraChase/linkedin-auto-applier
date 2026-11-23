"""
Remembered answers: questions you have answered (or approved) once are reused exactly next time.

Stored in config/answers.json (git-ignored, it is your personal data). You can edit that file by hand.
Priority when filling a form:  remembered answer  >  your config rules  >  AI.
"""
import json, os, re, time

from app_paths import home
PATH = os.path.join(home(), "config", "answers.json")


def normalize(label):
    s = (label or "").lower()
    s = re.sub(r"\*+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Memory:
    def __init__(self, path=PATH):
        self.path = path
        try:
            self.data = json.load(open(path, encoding="utf-8"))
        except Exception:
            self.data = {}

    def get(self, label, kind, options=None):
        """Remembered answer for this exact question, or None. For choices it must be one of the options."""
        rec = self.data.get(normalize(label))
        if not rec: return None
        ans = rec.get("answer")
        if not ans: return None
        if options:
            low = [o.lower().strip() for o in options]
            if ans.lower().strip() not in low: return None
            return options[low.index(ans.lower().strip())]
        return ans

    def learn(self, label, answer, kind, source="you"):
        answer = (answer or "").strip()
        key = normalize(label)
        if not key or not answer: return False
        old = self.data.get(key, {}).get("answer")
        self.data[key] = {"question": label.strip(), "answer": answer, "kind": kind, "source": source,
                          "saved": time.strftime("%Y-%m-%d %H:%M")}
        self.save()
        return old != answer

    def forget(self, label):
        self.data.pop(normalize(label), None)
        self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            json.dump(self.data, open(self.path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        except Exception:
            pass
