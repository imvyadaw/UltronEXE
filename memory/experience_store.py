import json, sqlite3, time
from pathlib import Path


class ExperienceStore:
    def __init__(self, path="storage/sqlite/ultron_experience.db"):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(p, check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS experiences(id INTEGER PRIMARY KEY,created REAL,success INTEGER,payload TEXT)"
        )
        self.db.commit()

    def add(self, x):
        self.db.execute(
            "INSERT INTO experiences(created,success,payload) VALUES(?,?,?)",
            (time.time(), int(bool(x.get("success"))), json.dumps(x, default=str)),
        )
        self.db.commit()
        return {"success": True}

    def recent(self, n=20):
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT payload FROM experiences ORDER BY created DESC LIMIT ?", (n,))
        ]
