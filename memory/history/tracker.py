"""Interaction tracker
===================
Logs individual interactions (one row per command/tool call/response),
distinct from memory/history/history.py which saves a whole conversation
*session* as one JSON blob. This is the finer-grained layer: it's what
lets Ultron answer "which tool do I use most", "what's my success rate on
X", or "show me everything that happened around 3pm yesterday" without
parsing every session's message JSON.

Typical use: core/executor.py or ai/tool_runtime.py logs each tool
execution here (name, arguments, success, latency); ai/ai_router.py could
log each chat turn's backend + latency the same way. Kept as its own
store rather than folded into history.py's session table, since the two
answer different questions (a session is "what was said", an interaction
is "what was done and how well").
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "interaction_history.db"


class InteractionTracker:
    """Append-only log of individual interactions, with simple aggregate stats."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                name TEXT,
                detail TEXT,
                success INTEGER,
                latency_ms REAL,
                created_at REAL
            )""")
        self._conn.commit()

    def log(
        self,
        name: str,
        kind: str = "tool",
        detail: Optional[Dict] = None,
        success: bool = True,
        latency_ms: Optional[float] = None,
    ) -> Dict:
        """Record one interaction. `kind` is a free-form category
        ("tool", "chat_turn", "agent_delegation", ...); `name` is the
        specific tool/agent/backend name; `detail` is any small JSON-able
        dict of extra context (arguments, error message, etc.)."""
        try:
            self._conn.execute(
                """INSERT INTO interactions (kind, name, detail, success, latency_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (kind, name, json.dumps(detail or {}), 1 if success else 0, latency_ms, time.time()),
            )
            self._conn.commit()
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def recent(self, limit: int = 20, kind: Optional[str] = None) -> Dict:
        """Most recent interactions, newest first."""
        try:
            cur = self._conn.cursor()
            if kind:
                cur.execute(
                    "SELECT kind, name, detail, success, latency_ms, created_at FROM interactions "
                    "WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                )
            else:
                cur.execute(
                    "SELECT kind, name, detail, success, latency_ms, created_at FROM interactions "
                    "ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            rows = cur.fetchall()
            return {"count": len(rows), "interactions": [self._row_to_dict(r) for r in rows]}
        except Exception as e:
            return {"error": str(e)}

    def stats_by_name(self, kind: Optional[str] = None) -> Dict:
        """Usage count + success rate + average latency, grouped by name -
        e.g. which tools get used most and how reliably."""
        try:
            cur = self._conn.cursor()
            if kind:
                cur.execute(
                    "SELECT name, COUNT(*), SUM(success), AVG(latency_ms) FROM interactions "
                    "WHERE kind=? GROUP BY name ORDER BY COUNT(*) DESC",
                    (kind,),
                )
            else:
                cur.execute(
                    "SELECT name, COUNT(*), SUM(success), AVG(latency_ms) FROM interactions "
                    "GROUP BY name ORDER BY COUNT(*) DESC"
                )
            out = {}
            for name, total, successes, avg_latency in cur.fetchall():
                out[name] = {
                    "uses": total,
                    "success_rate": round((successes or 0) / total, 3) if total else None,
                    "avg_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
                }
            return out
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _row_to_dict(row) -> Dict:
        kind, name, detail, success, latency_ms, created_at = row
        try:
            detail_obj = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            detail_obj = {}
        return {
            "kind": kind,
            "name": name,
            "detail": detail_obj,
            "success": bool(success),
            "latency_ms": latency_ms,
            "created_at": created_at,
        }


_tracker: Optional[InteractionTracker] = None


def get_interaction_tracker() -> InteractionTracker:
    global _tracker
    if _tracker is None:
        _tracker = InteractionTracker()
    return _tracker
