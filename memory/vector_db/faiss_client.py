"""FAISS client
============
🆓 FAISS-backed vector store - the backup fast-similarity-search backend
(used when chromadb isn't installed but faiss-cpu is). Same public shape
(add / similarity_search) as memory/vector_db/chroma_client.py and
memory/vector_db/vector_store.py, chosen automatically by
memory/vector_db/__init__.py.get_vector_store().

FAISS itself only holds vectors + integer ids in memory (with an on-disk
index file for persistence) - it has no built-in text/metadata storage,
so the actual text and category are kept alongside in a small SQLite
table (storage/sqlite/faiss_meta.db), looked up by id after FAISS returns
the nearest-neighbor ids.

Falls back gracefully: if faiss isn't installed, HAS_FAISS is False and
callers should use a different backend.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict

from ai.embeddings import embed, VECTOR_SIZE

INDEX_PATH = Path(__file__).resolve().parents[2] / "storage" / "cache" / "faiss_index.bin"
META_DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "faiss_meta.db"

try:
    import faiss
    import numpy as np

    HAS_FAISS = True
except Exception:
    faiss = None
    np = None
    HAS_FAISS = False


class FaissVectorStore:
    """FAISS flat (exact, brute-force) index for cosine-similarity search,
    with text/category metadata kept in a companion SQLite table. Flat
    index rather than an approximate one (IVF/HNSW) since a personal
    assistant's memory store is small (hundreds-to-low-thousands of
    entries) - exact search is fast enough and needs no training step."""

    def __init__(self):
        if not HAS_FAISS:
            raise RuntimeError(
                "faiss is not installed. Run `pip install faiss-cpu` to use this backend, "
                "or use memory/vector_db/vector_store.py's SQLite fallback instead."
            )
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        META_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        # IndexFlatIP (inner product) over L2-normalized vectors == cosine
        # similarity - ai/embeddings.py already L2-normalizes its output.
        if INDEX_PATH.exists():
            self._index = faiss.read_index(str(INDEX_PATH))
            if self._index.d != VECTOR_SIZE:
                # Stale index from before a VECTOR_SIZE change (e.g. the
                # 256->384 embeddings.py fix) - old vectors aren't
                # comparable to new ones anyway, so rebuild clean instead
                # of letting every future add() fail inside FAISS.
                from core.error_trace import log_swallowed as _lsw

                _lsw(
                    f"memory.vector_db.faiss_client: index dim {self._index.d} "
                    f"!= current VECTOR_SIZE {VECTOR_SIZE}, rebuilding fresh"
                )
                self._index = faiss.IndexFlatIP(VECTOR_SIZE)
                rebuilt_stale_index = True
        else:
            self._index = faiss.IndexFlatIP(VECTOR_SIZE)
            rebuilt_stale_index = False

        self._conn = sqlite3.connect(str(META_DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                faiss_id INTEGER PRIMARY KEY,
                text TEXT,
                category TEXT,
                created_at REAL
            )""")
        if rebuilt_stale_index:
            # New index's faiss_id sequence restarts at 0 - drop old meta
            # rows so they can't collide with (and return stale text for)
            # a fresh vector that lands on the same id.
            self._conn.execute("DELETE FROM meta")
        self._conn.commit()

    def _save_index(self) -> None:
        faiss.write_index(self._index, str(INDEX_PATH))

    def add(self, text: str, category: str = "general") -> Dict:
        try:
            vec = np.array([embed(text)], dtype="float32")
            faiss_id = self._index.ntotal
            self._index.add(vec)
            self._save_index()
            self._conn.execute(
                "INSERT INTO meta (faiss_id, text, category, created_at) VALUES (?, ?, ?, ?)",
                (faiss_id, text, category, time.time()),
            )
            self._conn.commit()
            return {"success": True, "id": faiss_id, "text": text, "category": category}
        except Exception as e:
            return {"error": str(e)}

    def similarity_search(self, query: str, top_k: int = 5) -> Dict:
        try:
            if self._index.ntotal == 0:
                return {"query": query, "results": []}
            vec = np.array([embed(query)], dtype="float32")
            n = min(top_k, self._index.ntotal)
            scores, ids = self._index.search(vec, n)

            results = []
            cur = self._conn.cursor()
            for faiss_id, score in zip(ids[0], scores[0]):
                if faiss_id < 0:
                    continue
                cur.execute("SELECT text, category FROM meta WHERE faiss_id=?", (int(faiss_id),))
                row = cur.fetchone()
                if not row:
                    continue
                text, category = row
                results.append(
                    {
                        "id": int(faiss_id),
                        "text": text,
                        "category": category,
                        "score": round(float(score), 4),
                    }
                )
            return {"query": query, "results": results}
        except Exception as e:
            return {"error": str(e)}

    def count(self) -> int:
        return self._index.ntotal
