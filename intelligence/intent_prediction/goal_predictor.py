"""
Goal Predictor (Phase 19.2 - Intent Prediction)
==================================================
One level above intent_predictor.py: a single intent ("coding",
"communicating") is a snapshot of the current moment, while a *goal*
("prepping for a meeting", "shipping a release") is a caller-defined
bundle of intents that tend to happen together over a stretch of
time. Goals are registered up front via register_goal(name,
expected_intents); infer_active_goal() then scores how well a recent
run of observed intents matches each registered goal, and reports
which expected intents are still missing.

This module doesn't invent goals on its own - nothing here does
unsupervised goal discovery. It only scores against goals a caller
(or, eventually, a UI letting the user define their own routines)
has explicitly told it about.

Storage: database/intent_prediction.db, table goals.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "intent_prediction.db"

_instance: Optional["GoalPredictor"] = None
_instance_lock = threading.Lock()


class GoalPredictor:
    """Registry of named goals (as sets of expected intents) plus scoring
    of recent intent activity against them."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                name TEXT,
                expected_intents TEXT,
                created_at REAL
            )""")
        self._conn.commit()

    # -- registry -----------------------------------------------------------
    def register_goal(self, name: str, expected_intents: List[str]) -> Dict:
        """Define a goal as an unordered set of intents that, seen together
        recently, suggest the user is pursuing it. Re-registering an
        existing name overwrites its expected intents."""
        if not name or not expected_intents:
            return {"error": "name and expected_intents required"}
        existing = self._find_by_name(name)
        goal_id = existing["id"] if existing else uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO goals (id, name, expected_intents, created_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET expected_intents = excluded.expected_intents""",
                (goal_id, name, json.dumps(expected_intents), now),
            )
            self._conn.commit()
        return self.get_goal(goal_id)

    def delete_goal(self, goal_id: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            self._conn.commit()
        return {"success": True, "id": goal_id}

    def get_goal(self, goal_id: str) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, name, expected_intents, created_at FROM goals WHERE id = ?", (goal_id,)
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no goal with id {goal_id}"}
        return self._row_to_dict(row)

    def list_goals(self) -> List[Dict]:
        with self._lock:
            cur = self._conn.execute("SELECT id, name, expected_intents, created_at FROM goals")
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def _find_by_name(self, name: str) -> Optional[Dict]:
        with self._lock:
            cur = self._conn.execute("SELECT id, name, expected_intents, created_at FROM goals WHERE name = ?", (name,))
            row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    # -- inference ----------------------------------------------------------
    def infer_active_goal(self, recent_intents: List[str]) -> List[Dict]:
        """Score every registered goal against a recent run of observed
        intents (most recent last). Returns all goals ranked by match
        score (fraction of the goal's expected intents seen recently),
        each with which expected intents are still missing."""
        seen = set(recent_intents)
        results = []
        for goal in self.list_goals():
            expected = set(goal["expected_intents"])
            if not expected:
                continue
            matched = expected & seen
            score = len(matched) / len(expected)
            results.append(
                {
                    "goal_id": goal["id"],
                    "name": goal["name"],
                    "score": round(score, 4),
                    "matched_intents": sorted(matched),
                    "missing_intents": sorted(expected - matched),
                    "complete": score >= 1.0,
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    @staticmethod
    def _row_to_dict(row) -> Dict:
        try:
            expected = json.loads(row[2]) if row[2] else []
        except Exception:
            expected = []
        return {"id": row[0], "name": row[1], "expected_intents": expected, "created_at": row[3]}


def get_goal_predictor() -> GoalPredictor:
    """Process-wide GoalPredictor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GoalPredictor()
    return _instance
