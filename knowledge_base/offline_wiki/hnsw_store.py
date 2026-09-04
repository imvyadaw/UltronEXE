"""Offline knowledge HNSW store
=============================
Approximate-nearest-neighbor vector index for the offline knowledge base
(knowledge_base/offline_wiki/ingest.py fills it, search.py queries it).

This is a DIFFERENT backend from memory/vector_db/*.py on purpose: those
three (vector_store.py's SQLite, chroma_client.py, faiss_client.py's flat
IndexFlatIP) are all explicitly documented as sized for a personal
assistant's own notes/memories - "hundreds to low thousands" of rows,
either brute-force Python similarity or an exact-search flat index. An
offline knowledge base built from a Wikipedia-scale dump is 100k-1M+
entries, where brute-force cosine over every row in Python, or even an
exact flat FAISS index, gets slow. HNSW (hierarchical navigable small
world graph) trades a small amount of recall for sub-linear query time
at that scale, which is the actual point of this module.

Falls back gracefully: if hnswlib isn't installed, HAS_HNSWLIB is False
and get_offline_kb() (in __init__.py) reports the KB as unavailable
rather than raising - same HAS_<DEP> convention as faiss_client.py.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List

from ai.embeddings import embed, VECTOR_SIZE

INDEX_PATH = Path(__file__).resolve().parents[2] / "storage" / "cache" / "offline_wiki_hnsw.bin"
META_DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "offline_wiki_meta.db"

# Generous headroom over Tier A's ~240k intro-paragraph vectors so the
# index doesn't need resizing mid-ingest (resizing is possible with
# hnswlib but simplest to just size it up front for the compact tier).
MAX_ELEMENTS = 400_000

try:
    import hnswlib

    HAS_HNSWLIB = True
except Exception:
    hnswlib = None
    HAS_HNSWLIB = False


class OfflineWikiStore:
    """HNSW index + companion SQLite metadata table (title, intro text,
    source url) for the offline knowledge base. Same add()/search() shape
    as memory/vector_db's backends so callers don't need to care which
    store they're talking to."""

    def __init__(self):
        if not HAS_HNSWLIB:
            raise RuntimeError(
                "hnswlib is not installed. Run `pip install hnswlib` to use the "
                "offline knowledge base, or leave ULTRON_OFFLINE_KB_ENABLED unset."
            )
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        META_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        self._index = hnswlib.Index(space="cosine", dim=VECTOR_SIZE)

        self._conn = sqlite3.connect(str(META_DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                hnsw_id INTEGER PRIMARY KEY,
                title TEXT,
                text TEXT,
                url TEXT,
                created_at REAL
            )""")
        self._conn.commit()

        cur = self._conn.execute("SELECT COUNT(*), COALESCE(MAX(hnsw_id), -1) FROM meta")
        count, max_id = cur.fetchone()
        self._next_id = max_id + 1

        if INDEX_PATH.exists() and count > 0:
            self._index.load_index(str(INDEX_PATH), max_elements=MAX_ELEMENTS)
            if self._index.dim != VECTOR_SIZE:
                # Stale index from before a VECTOR_SIZE change - old
                # vectors aren't comparable to new ones, rebuild clean
                # rather than let every future add_items() fail.
                from core.error_trace import log_swallowed as _lsw

                _lsw(
                    f"knowledge_base.offline_wiki.hnsw_store: index dim "
                    f"{self._index.dim} != current VECTOR_SIZE {VECTOR_SIZE}, "
                    f"rebuilding fresh"
                )
                self._index.init_index(max_elements=MAX_ELEMENTS, ef_construction=200, M=16)
                self._conn.execute("DELETE FROM meta")
                self._conn.commit()
                self._next_id = 0
        else:
            self._index.init_index(max_elements=MAX_ELEMENTS, ef_construction=200, M=16)

        # ef (query-time search width) - higher = better recall, slower
        # query. 64 is a reasonable default for a few-hundred-thousand
        # element index; raise if search() results feel too approximate.
        self._index.set_ef(64)

    def add(self, title: str, text: str, url: str = "") -> Dict:
        """Embed `text` and add it to the index under `title`/`url` metadata.
        Never raises - returns {"error": ...} on failure, per project
        convention (see memory/vector_db/faiss_client.py's add())."""
        try:
            vec = embed(text)
            hnsw_id = self._next_id
            self._index.add_items([vec], [hnsw_id])
            self._conn.execute(
                "INSERT INTO meta (hnsw_id, title, text, url, created_at) VALUES (?, ?, ?, ?, ?)",
                (hnsw_id, title, text, url, time.time()),
            )
            self._conn.commit()
            self._next_id += 1
            return {"success": True, "id": hnsw_id, "title": title}
        except Exception as e:
            return {"error": str(e)}

    def add_batch(self, records: List[Dict]) -> Dict:
        """Bulk-add [{"title":..., "text":..., "url":...}, ...]. Embeds and
        inserts in one pass - used by ingest.py so a multi-hour ingest run
        isn't doing a Python-level commit per single article."""
        try:
            vecs = [embed(r["text"]) for r in records]
            ids = list(range(self._next_id, self._next_id + len(records)))
            self._index.add_items(vecs, ids)
            rows = [(i, r.get("title", ""), r["text"], r.get("url", ""), time.time()) for i, r in zip(ids, records)]
            self._conn.executemany(
                "INSERT INTO meta (hnsw_id, title, text, url, created_at) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
            self._next_id += len(records)
            return {"success": True, "added": len(records)}
        except Exception as e:
            return {"error": str(e)}

    def similarity_search(self, query: str, top_k: int = 5) -> Dict:
        """Return the top_k stored entries most similar to `query`."""
        try:
            if self._index.get_current_count() == 0:
                return {"query": query, "results": []}
            query_vec = embed(query)
            k = min(top_k, self._index.get_current_count())
            labels, distances = self._index.knn_query([query_vec], k=k)
            results = []
            for hnsw_id, dist in zip(labels[0], distances[0]):
                row = self._conn.execute(
                    "SELECT title, text, url FROM meta WHERE hnsw_id = ?", (int(hnsw_id),)
                ).fetchone()
                if row is None:
                    continue
                title, text, url = row
                # hnswlib's "cosine" space returns a distance (1 - cosine
                # similarity), so convert back to a similarity score for
                # a consistent shape with memory/vector_db's stores.
                results.append(
                    {
                        "id": int(hnsw_id),
                        "title": title,
                        "text": text,
                        "url": url,
                        "score": round(1.0 - float(dist), 4),
                    }
                )
            return {"query": query, "results": results}
        except Exception as e:
            return {"error": str(e)}

    def count(self) -> Dict:
        try:
            return {"count": self._index.get_current_count()}
        except Exception as e:
            return {"error": str(e)}

    def save(self) -> Dict:
        """Persist the index to disk. ingest.py calls this periodically
        (not after every single add) since HNSW save is a full-file write."""
        try:
            self._index.save_index(str(INDEX_PATH))
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
