"""
Temporal Graph (Phase 19.7 - Knowledge Graph)
==================================================
graph_store.py only keeps first_seen_at/last_seen_at on each node and
edge - a single timestamp, overwritten every time. That answers "when
was X last mentioned" but not "show me the timeline for X" or "what
happened in the last 7 days". This module adds the chronological
layer on top: every node/edge touch knowledge_graph_engine.py's
ingest() pipeline makes also gets logged here as a standalone event,
so history survives even though graph_store.py's own timestamps
don't accumulate.

This module only logs and reads events - it never decides what
counts as a touch (that's the engine's job) or mutates the graph
itself (graph_store.py's job).

Storage: database/knowledge_graph.db, table kg_events.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "knowledge_graph.db"

_instance: Optional["TemporalGraph"] = None
_instance_lock = threading.Lock()


class TemporalGraph:
    """Append-only event log for graph touches, plus the timeline/
    recency queries built on top of it."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS kg_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id INTEGER,
                node_name TEXT,
                edge_id INTEGER,
                event_type TEXT,
                detail TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    def log_event(
        self,
        event_type: str,
        node_id: Optional[int] = None,
        node_name: Optional[str] = None,
        edge_id: Optional[int] = None,
        detail: Optional[Dict] = None,
    ) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO kg_events (node_id, node_name, edge_id, event_type, detail, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (node_id, node_name, edge_id, event_type, json.dumps(detail or {}), now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_timeline(self, node_name: str, limit: int = 50) -> List[Dict]:
        """Every logged event for a node, most recent first - the raw
        material for "when did we last talk about X" or "show me
        X's history"."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT event_id, node_id, node_name, edge_id, event_type, detail, timestamp
                   FROM kg_events WHERE node_name = ? ORDER BY timestamp DESC LIMIT ?""",
                (node_name.lower(), limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def recent_activity(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """Every event within the last `days` days, most recent
        first - "what's been going on lately" across the whole graph."""
        cutoff = time.time() - (days * 86400)
        with self._lock:
            rows = self._conn.execute(
                """SELECT event_id, node_id, node_name, edge_id, event_type, detail, timestamp
                   FROM kg_events WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def activity_by_period(self, start_ts: float, end_ts: float, limit: int = 200) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT event_id, node_id, node_name, edge_id, event_type, detail, timestamp
                   FROM kg_events WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp ASC LIMIT ?""",
                (start_ts, end_ts, limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def most_active_names(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """node_name -> event count over the window, busiest first -
        a cheap proxy for "who/what's trending" without needing
        graph_query.py's edge-weight notion of centrality."""
        cutoff = time.time() - (days * 86400)
        with self._lock:
            rows = self._conn.execute(
                """SELECT node_name, COUNT(*) as event_count FROM kg_events
                   WHERE timestamp >= ? AND node_name IS NOT NULL
                   GROUP BY node_name ORDER BY event_count DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [{"node_name": r[0], "event_count": r[1]} for r in rows]

    @staticmethod
    def _row_to_event(row) -> Dict:
        event_id, node_id, node_name, edge_id, event_type, detail_json, timestamp = row
        try:
            detail = json.loads(detail_json) if detail_json else {}
        except Exception:
            detail = {}
        return {
            "event_id": event_id,
            "node_id": node_id,
            "node_name": node_name,
            "edge_id": edge_id,
            "event_type": event_type,
            "detail": detail,
            "timestamp": timestamp,
        }


def get_temporal_graph() -> TemporalGraph:
    """Process-wide TemporalGraph singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TemporalGraph()
    return _instance
