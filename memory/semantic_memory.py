"""Semantic memory
================
General knowledge/concepts Ultron has learned, independent of any one
event or timestamp - "a VPN encrypts network traffic", "Alex is the
user's manager". Distinct from:
- memory/episodic_memory.py: timestamped things that *happened*.
- memory/long_term/long_term.py: durable key/value facts *about the user*.
Semantic memory instead stores definitions plus typed relations between
concepts (concept --relation--> related_concept), which is what lets
"who is Alex" and "who does the user report to" both resolve to the
same underlying fact.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "sqlite" / "semantic_memory.db"

_semantic_memory: Optional["SemanticMemory"] = None


class SemanticMemory:
    """Concepts, definitions, and relations between them."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS concepts (
                concept TEXT PRIMARY KEY,
                definition TEXT,
                updated_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept TEXT,
                relation TEXT,
                related_concept TEXT,
                created_at REAL
            )""")
        self._conn.commit()

    def add_concept(self, concept: str, definition: str) -> Dict:
        """Define or redefine a concept."""
        try:
            self._conn.execute(
                "INSERT INTO concepts (concept, definition, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(concept) DO UPDATE SET definition = excluded.definition, updated_at = excluded.updated_at",
                (concept.lower(), definition, time.time()),
            )
            self._conn.commit()
            return {"success": True, "concept": concept}
        except Exception as e:
            return {"error": str(e)}

    def define(self, concept: str) -> Dict:
        """Look up a concept's stored definition."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT definition, updated_at FROM concepts WHERE concept = ?", (concept.lower(),))
            row = cur.fetchone()
            if not row:
                return {"error": f"No definition stored for '{concept}'"}
            return {"concept": concept, "definition": row[0], "updated_at": row[1]}
        except Exception as e:
            return {"error": str(e)}

    def relate(self, concept: str, relation: str, related_concept: str) -> Dict:
        """Store a relation, e.g. relate('Alex', 'is the manager of', 'user')."""
        try:
            self._conn.execute(
                "INSERT INTO relations (concept, relation, related_concept, created_at) VALUES (?, ?, ?, ?)",
                (concept, relation, related_concept, time.time()),
            )
            self._conn.commit()
            return {"success": True, "concept": concept, "relation": relation, "related_concept": related_concept}
        except Exception as e:
            return {"error": str(e)}

    def get_related(self, concept: str) -> Dict:
        """All stored relations where `concept` is either side."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT concept, relation, related_concept FROM relations WHERE concept = ? OR related_concept = ?",
                (concept, concept),
            )
            rows = cur.fetchall()
            relations = [{"concept": r[0], "relation": r[1], "related_concept": r[2]} for r in rows]
            return {"concept": concept, "count": len(relations), "relations": relations}
        except Exception as e:
            return {"error": str(e)}

    def search_concepts(self, query: str) -> Dict:
        """Substring search over concept names and definitions."""
        try:
            like = f"%{query.lower()}%"
            cur = self._conn.cursor()
            cur.execute(
                "SELECT concept, definition FROM concepts WHERE concept LIKE ? OR definition LIKE ?", (like, like)
            )
            rows = cur.fetchall()
            results = [{"concept": r[0], "definition": r[1]} for r in rows]
            return {"query": query, "count": len(results), "results": results}
        except Exception as e:
            return {"error": str(e)}

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """Thin adapter over search_concepts() for callers (e.g.
        reasoning/evidence.py) that expect a flat list of
        {content, score} hits rather than the {query, count, results}
        shape search_concepts() returns."""
        found = self.search_concepts(query)
        rows = found.get("results", []) if isinstance(found, dict) else []
        hits = [{"content": f"{r['concept']}: {r['definition']}", "score": 0.4} for r in rows]
        return hits[:top_k]


def get_semantic_memory() -> "SemanticMemory":
    """Process-wide singleton, same pattern as core.brain.get_brain() /
    core.events.get_event_bus(). Was missing before, which meant
    reasoning/evidence.py's `from memory.semantic_memory import
    get_semantic_memory` silently failed every time."""
    global _semantic_memory
    if _semantic_memory is None:
        _semantic_memory = SemanticMemory()
    return _semantic_memory
