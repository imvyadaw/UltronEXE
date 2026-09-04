"""Vector store
============
Semantic-ish search over saved notes/facts using the embeddings from
ai/embeddings.py. Stored in SQLite (vector serialized as JSON) - fine
for a personal assistant's scale (hundreds to low thousands of rows);
similarity is computed in Python at query time.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict

from ai.embeddings import embed, cosine_similarity

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "vector_store.db"


class VectorStore:
    """Store text + its embedding, then find the most similar stored texts to a query."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT,
                vector TEXT,
                category TEXT,
                created_at REAL
            )""")
        self._conn.commit()

    def add(self, text: str, category: str = "general") -> Dict:
        """Embed and store a piece of text."""
        try:
            vec = embed(text)
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO vectors (text, vector, category, created_at) VALUES (?, ?, ?, ?)",
                (text, json.dumps(vec), category, time.time()),
            )
            self._conn.commit()
            return {"success": True, "id": cur.lastrowid, "text": text}
        except Exception as e:
            return {"error": str(e)}

    def similarity_search(self, query: str, top_k: int = 5, category: str = None) -> Dict:
        """Return the top_k stored texts most similar to `query`."""
        try:
            query_vec = embed(query)
            cur = self._conn.cursor()
            if category:
                cur.execute("SELECT id, text, vector, category FROM vectors WHERE category = ?", (category,))
            else:
                cur.execute("SELECT id, text, vector, category FROM vectors")
            rows = cur.fetchall()

            scored = []
            for row_id, text, vec_json, cat in rows:
                stored_vec = json.loads(vec_json)
                score = cosine_similarity(query_vec, stored_vec)
                scored.append({"id": row_id, "text": text, "category": cat, "score": round(score, 4)})

            scored.sort(key=lambda r: r["score"], reverse=True)
            return {"query": query, "results": scored[:top_k]}
        except Exception as e:
            return {"error": str(e)}

    def delete(self, entry_id: int) -> Dict:
        """Delete a stored entry by id."""
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM vectors WHERE id = ?", (entry_id,))
            self._conn.commit()
            return {"success": True, "deleted_id": entry_id, "rows_affected": cur.rowcount}
        except Exception as e:
            return {"error": str(e)}

    def count(self) -> Dict:
        """Count stored entries."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vectors")
            return {"count": cur.fetchone()[0]}
        except Exception as e:
            return {"error": str(e)}
