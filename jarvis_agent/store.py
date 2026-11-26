"""Long-term memory, kept in one local JSON file (data/memory.json).

Holds: last successful run, links already sent (14 days), working feed URLs,
and the agent's own lessons from earlier runs.
"""
import datetime
import json
import os

from .config import DATA_DIR, LESSONS_KEPT

PATH = os.path.join(DATA_DIR, "memory.json")
SENT_DAYS = 14


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class Memory:
    def __init__(self, path=PATH):
        self.path = path
        self.data = {"last_run": None, "sent": {}, "source_urls": {}, "lessons": []}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data.update(json.load(f))

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)

    # --- last run -------------------------------------------------------
    def last_run(self):
        val = self.data.get("last_run")
        if val:
            return datetime.datetime.fromisoformat(val)
        return _now() - datetime.timedelta(days=3)

    def set_last_run(self, when=None):
        self.data["last_run"] = (when or _now()).isoformat()

    # --- sent links -----------------------------------------------------
    def prune_sent(self):
        cutoff = _now() - datetime.timedelta(days=SENT_DAYS)
        self.data["sent"] = {
            url: ts for url, ts in self.data["sent"].items()
            if datetime.datetime.fromisoformat(ts) >= cutoff
        }

    def was_sent(self, url):
        return url in self.data["sent"]

    def mark_sent(self, urls):
        now = _now().isoformat()
        for url in urls:
            self.data["sent"][url] = now

    # --- feed URLs that worked (self-healing) ---------------------------
    def source_url(self, name, default):
        return self.data["source_urls"].get(name, default)

    def set_source_url(self, name, url):
        self.data["source_urls"][name] = url

    # --- lessons the agent writes for its future self -------------------
    def lessons(self):
        return list(self.data["lessons"])

    def add_lesson(self, text):
        text = " ".join(str(text).split())[:300]
        if not text:
            return
        entry = {"date": _now().date().isoformat(), "lesson": text}
        self.data["lessons"] = (self.data["lessons"] + [entry])[-LESSONS_KEPT:]
