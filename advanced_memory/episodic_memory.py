"""
Advanced episodic memory
=========================
memory/episodic_memory.py already logs timestamped events to SQLite -
that storage and its exact-match/substring queries (recent_events(),
events_between(), search_events()) are NOT reimplemented or modified
here. What's missing there and added here:

    - importance scoring per event, feeding forgetting_curve.py so a
      throwaway event fades and a significant one doesn't
    - a memory_graph.py node per event, so an episode can be linked to
      the concepts it taught (semantic_memory.py), the place it
      happened (spatial_memory.py) and the routine it's an instance of
      (temporal_memory.py)
    - embedding-backed recall_similar() via memory/vector_db - "when
      did something like this happen before" instead of only exact
      substring search

This module owns one extra table (event_id -> importance/graph node,
in its own DB) and never touches memory/episodic_memory.py's schema -
same "wrap, don't modify" guarantee as every prior Phase 17 package.
"""

import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from memory.episodic_memory import EpisodicMemory
from memory.vector_db.vector_store import VectorStore

from advanced_memory.memory_graph import get_memory_graph
from advanced_memory.forgetting_curve import get_forgetting_curve

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "advanced_episodic_memory.db"
VECTOR_CATEGORY = "episodic"

_advanced_episodic: Optional["AdvancedEpisodicMemory"] = None
_lock = Lock()


class AdvancedEpisodicMemory:
    """Do not construct directly - use get_advanced_episodic_memory()."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS episode_meta (
                event_id INTEGER PRIMARY KEY,
                importance REAL,
                vector_id INTEGER,
                created_at REAL
            )""")
        self._conn.commit()
        self._write_lock = Lock()

        self._base = EpisodicMemory()
        self._graph = get_memory_graph()
        self._curve = get_forgetting_curve()
        self._vectors = VectorStore()

    # -- writing ---------------------------------------------------------------
    def record_event(
        self,
        event: str,
        context: str = "",
        tags: str = "",
        importance: float = 0.5,
        link_to: Optional[List[str]] = None,
    ) -> Dict:
        """Records the event via the base module (unchanged behavior),
        then layers on graph node + decay tracking + embedding.
        `link_to` is an optional list of other graph node_ids
        (e.g. "place:home", "concept:deployment") to connect immediately
        - use link_event() later for anything not known yet at write time."""
        base_result = self._base.record_event(event, context, tags)
        if "error" in base_result:
            return base_result

        row = self._latest_event_row()
        if row is None:
            return {"error": "event recorded but could not be re-read for id"}
        event_id = row["id"]
        node_id = f"episodic:{event_id}"

        vector_result = self._vectors.add(f"{event} {context}".strip(), category=VECTOR_CATEGORY)
        vector_id = vector_result.get("id") if "error" not in vector_result else None

        importance = max(0.0, min(1.0, importance))
        try:
            with self._write_lock:
                self._conn.execute(
                    "INSERT INTO episode_meta (event_id, importance, vector_id, created_at) VALUES (?, ?, ?, ?)",
                    (event_id, importance, vector_id, time.time()),
                )
                self._conn.commit()
        except Exception as e:
            return {"error": str(e)}

        self._graph.add_node(
            node_id, "episodic", event, metadata={"context": context, "tags": tags, "importance": importance}
        )
        self._curve.track(node_id, importance=importance)

        for target in link_to or []:
            self._graph.add_edge(node_id, target, "occurred_with")

        return {**base_result, "event_id": event_id, "node_id": node_id, "importance": importance}

    def link_event(self, event_id: int, target_node_id: str, relation: str = "related_to") -> Dict:
        """Connect an already-recorded event to any other graph node -
        a place (spatial_memory.py), a concept (semantic_memory.py), a
        routine (temporal_memory.py), or another episode."""
        return self._graph.add_edge(f"episodic:{event_id}", target_node_id, relation)

    # -- reading -----------------------------------------------------------------
    def recall_event(self, event_id: int) -> Dict:
        """Fetch one event by id and reinforce it in the forgetting
        curve - unlike recent_events()/search_events() below, this is
        a deliberate recall and should make the memory stickier."""
        try:
            cur = self._base._conn.cursor()
            cur.execute("SELECT id, event, context, tags, occurred_at FROM episodes WHERE id = ?", (event_id,))
            row = cur.fetchone()
            if not row:
                return {"error": f"No episode with id {event_id}"}
            node_id = f"episodic:{event_id}"
            self._curve.record_access(node_id)
            retention = self._curve.retention(node_id)
            return {
                "id": row[0],
                "event": row[1],
                "context": row[2],
                "tags": row[3],
                "occurred_at": row[4],
                "importance": self._get_importance(event_id),
                "retention": retention.get("retention"),
            }
        except Exception as e:
            return {"error": str(e)}

    def recent_events(self, limit: int = 20) -> Dict:
        """Passthrough to the base module - listing recent events isn't
        a deliberate single-memory recall, so it doesn't reinforce
        forgetting_curve.py on its own (avoids every list view silently
        making everything unforgettable)."""
        return self._base.recent_events(limit)

    def search_events(self, query: str, limit: int = 20) -> Dict:
        return self._base.search_events(query, limit)

    def recall_similar(self, query: str, top_k: int = 5) -> Dict:
        """Embedding-based recall - "something like this happened
        before" rather than requiring the exact words search_events()
        needs. Each hit is enriched with its current retention score so
        a fresh strong match can be told apart from an all-but-forgotten
        one."""
        hits = self._vectors.similarity_search(query, top_k=top_k, category=VECTOR_CATEGORY)
        if "error" in hits:
            return hits
        enriched = []
        for hit in hits.get("results", []):
            event_id = self._event_id_for_vector(hit["id"])
            entry = dict(hit)
            if event_id is not None:
                node_id = f"episodic:{event_id}"
                ret = self._curve.retention(node_id)
                entry["event_id"] = event_id
                entry["retention"] = ret.get("retention") if "error" not in ret else None
            enriched.append(entry)
        return {"query": query, "count": len(enriched), "results": enriched}

    def consolidation_candidates(self, min_importance: float = 0.7, min_access: int = 2) -> Dict:
        """Episodes worth promoting to semantic memory: important
        and/or repeatedly recalled. Read by memory_consolidator.py -
        this module never promotes anything itself."""
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT event_id, importance FROM episode_meta WHERE importance >= ?", (min_importance,))
            candidates = []
            for event_id, importance in cur.fetchall():
                node_id = f"episodic:{event_id}"
                ret = self._curve.retention(node_id)
                access_count = ret.get("access_count", 0) if "error" not in ret else 0
                if importance >= min_importance or access_count >= min_access:
                    row = self._event_row(event_id)
                    if row:
                        candidates.append(
                            {
                                "event_id": event_id,
                                "event": row["event"],
                                "importance": importance,
                                "access_count": access_count,
                            }
                        )
            return {"count": len(candidates), "candidates": candidates}
        except Exception as e:
            return {"error": str(e)}

    # -- internal --------------------------------------------------------------
    def _latest_event_row(self) -> Optional[Dict]:
        cur = self._base._conn.cursor()
        cur.execute("SELECT id, event, context, tags, occurred_at FROM episodes ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "event": row[1], "context": row[2], "tags": row[3], "occurred_at": row[4]}

    def _event_row(self, event_id: int) -> Optional[Dict]:
        cur = self._base._conn.cursor()
        cur.execute("SELECT id, event, context, tags, occurred_at FROM episodes WHERE id = ?", (event_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "event": row[1], "context": row[2], "tags": row[3], "occurred_at": row[4]}

    def _get_importance(self, event_id: int) -> Optional[float]:
        cur = self._conn.cursor()
        cur.execute("SELECT importance FROM episode_meta WHERE event_id = ?", (event_id,))
        row = cur.fetchone()
        return row[0] if row else None

    def _event_id_for_vector(self, vector_id: int) -> Optional[int]:
        cur = self._conn.cursor()
        cur.execute("SELECT event_id FROM episode_meta WHERE vector_id = ?", (vector_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_advanced_episodic_memory() -> AdvancedEpisodicMemory:
    """Process-wide singleton, same pattern as memory_graph.get_memory_graph()."""
    global _advanced_episodic
    with _lock:
        if _advanced_episodic is None:
            _advanced_episodic = AdvancedEpisodicMemory()
        return _advanced_episodic
