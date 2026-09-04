import sqlite3
from pathlib import Path


class KnowledgeGraph:
    def __init__(self, path="storage/sqlite/ultron_knowledge.db"):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(p, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS edges(s,p,o,UNIQUE(s,p,o))")
        self.db.commit()

    def add(self, s, p, o):
        self.db.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?)", (s, p, o))
        self.db.commit()

    def neighbors(self, s):
        return self.db.execute("SELECT p,o FROM edges WHERE s=?", (s,)).fetchall()
