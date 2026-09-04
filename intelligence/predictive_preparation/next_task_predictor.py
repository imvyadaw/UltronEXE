"""
Next Task Predictor (Phase 20.2 - Predictive Preparation)
==================================================
Learns what the user tends to do, and when, so predictive_engine.py
has something concrete to act on before the user asks - "after
opening VS Code, a terminal command usually follows", "at 9pm this
user usually asks for a summary of the day". Two independent signals
feed every prediction:

    transitions  - what task_type usually follows the current one,
                   learned from an in-memory-then-persisted sequence
                   of observed tasks (a simple first-order Markov
                   chain, not a learned model - same "deliberately
                   simple/heuristic" posture as urgency_calculator.py)
    time-of-day  - what task_type usually happens around this hour,
                   independent of whatever just happened, for the
                   common case of predicting the *first* thing in a
                   session (no current_task to chain from yet)

record_task() is the only way this module learns - it must be called
by whatever elsewhere in ULTRON knows a task actually started (tool
dispatcher, conversation engine, app control, etc). Phase 20.2 does
not wire that call in anywhere itself, in keeping with "purely
additive" - predictive_engine.py exposes the same call at its own
entry point for a caller that wants one integration point instead of
importing this module directly.

Storage: database/predictive_preparation.db, tables task_events (raw
log, one row per observed task) and transition_counts (aggregated
from_task -> to_task counts, updated incrementally on each
record_task() rather than recomputed from task_events every time).

Session gap: two tasks are only treated as a transition of one into
the other if they happened within _SESSION_GAP_SECONDS of each other.
A task recorded after a long gap starts a fresh chain instead of
being wrongly linked to whatever the user was doing hours earlier.
"""

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.logger import get_logger

logger = get_logger("ultron.next_task_predictor")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "predictive_preparation.db"

_instance: Optional["NextTaskPredictor"] = None
_instance_lock = threading.Lock()

# two tasks more than this far apart are treated as unrelated (a new
# chain starts) rather than as a learned transition
_SESSION_GAP_SECONDS = 7200.0

# how a prediction blends transition history against time-of-day
# history when both current_task and clock time are available
_TRANSITION_WEIGHT = 0.65
_TIME_OF_DAY_WEIGHT = 0.35

# how wide an hour window counts as "this time of day" when scoring
# historical task_events for the time-of-day signal
_HOUR_WINDOW = 1


class NextTaskPredictor:
    """record_task() to learn; predict_next() to ask what's likely next."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT,
                category TEXT,
                hour INTEGER,
                day_of_week INTEGER,
                context_json TEXT,
                timestamp REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS transition_counts (
                from_task TEXT,
                to_task TEXT,
                count INTEGER,
                last_seen REAL,
                PRIMARY KEY (from_task, to_task)
            )""")
        self._conn.commit()
        # in-memory only - which task was last recorded and when, so
        # record_task() knows whether this is a continuation of a
        # chain or the start of a new one. Resets harmlessly on
        # restart, same spirit as event_detector.py's dedup cache.
        self._last_task: Optional[Tuple[str, float]] = None

    def record_task(self, task_type: str, category: Optional[str] = None, context: Optional[Dict] = None) -> Dict:
        import json

        now = time.time()
        dt = datetime.fromtimestamp(now)

        with self._lock:
            self._conn.execute(
                """INSERT INTO task_events (task_type, category, hour, day_of_week, context_json, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_type, category, dt.hour, dt.weekday(), json.dumps(context or {}), now),
            )
            self._conn.commit()

            last_task, last_ts = self._last_task if self._last_task else (None, None)
            linked = False
            if last_task is not None and (now - last_ts) <= _SESSION_GAP_SECONDS:
                self._conn.execute(
                    """INSERT INTO transition_counts (from_task, to_task, count, last_seen)
                       VALUES (?, ?, 1, ?)
                       ON CONFLICT(from_task, to_task)
                       DO UPDATE SET count = count + 1, last_seen = excluded.last_seen""",
                    (last_task, task_type, now),
                )
                self._conn.commit()
                linked = True

            self._last_task = (task_type, now)

        return {
            "task_type": task_type,
            "category": category,
            "timestamp": now,
            "linked_from": last_task if linked else None,
        }

    def predict_next(self, current_task: Optional[str] = None, context: Optional[Dict] = None, top_n: int = 3) -> Dict:
        context = context or {}
        reasons: List[str] = []

        if current_task is None:
            with self._lock:
                if self._last_task is not None and (time.time() - self._last_task[1]) <= _SESSION_GAP_SECONDS:
                    current_task = self._last_task[0]
                    reasons.append(f"no current_task given - using recent task '{current_task}' from session")
                else:
                    reasons.append("no current_task given and no recent task in session")

        now = context.get("timestamp", time.time())
        dt = datetime.fromtimestamp(now)
        hour = dt.hour

        transition_scores = self._transition_scores(current_task)
        if transition_scores:
            reasons.append(f"found transition history from '{current_task}' ({len(transition_scores)} candidate(s))")

        time_scores = self._time_of_day_scores(hour)
        if time_scores:
            reasons.append(f"found time-of-day history around hour {hour} ({len(time_scores)} candidate(s))")

        if not transition_scores and not time_scores:
            fallback = self._overall_frequency_scores()
            if fallback:
                reasons.append("no transition or time-of-day match - falling back to overall task frequency")
                combined = fallback
            else:
                reasons.append("no task history at all yet - nothing to predict from")
                combined = {}
        else:
            combined = self._combine(transition_scores, time_scores)

        categories = self._categories_for_tasks(combined.keys())
        predictions = [
            {"task_type": t, "category": categories.get(t), "confidence": round(min(1.0, s), 3)}
            for t, s in sorted(combined.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        ]

        return {"predictions": predictions, "current_task": current_task, "reasons": reasons}

    def get_stats(self) -> Dict:
        with self._lock:
            total_events = self._conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
            distinct_tasks = self._conn.execute("SELECT COUNT(DISTINCT task_type) FROM task_events").fetchone()[0]
            total_transitions = self._conn.execute("SELECT COUNT(*) FROM transition_counts").fetchone()[0]
        return {
            "total_events": total_events,
            "distinct_task_types": distinct_tasks,
            "total_transition_edges": total_transitions,
        }

    def get_recent_events(self, limit: int = 20) -> List[Dict]:
        import json

        with self._lock:
            rows = self._conn.execute(
                """SELECT task_type, category, hour, day_of_week, context_json, timestamp
                   FROM task_events ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        events = []
        for task_type, category, hour, day_of_week, context_json, timestamp in rows:
            try:
                context = json.loads(context_json) if context_json else {}
            except Exception:
                context = {}
            events.append(
                {
                    "task_type": task_type,
                    "category": category,
                    "hour": hour,
                    "day_of_week": day_of_week,
                    "context": context,
                    "timestamp": timestamp,
                }
            )
        return events

    def _transition_scores(self, current_task: Optional[str]) -> Dict[str, float]:
        if current_task is None:
            return {}
        with self._lock:
            rows = self._conn.execute(
                "SELECT to_task, count FROM transition_counts WHERE from_task = ?",
                (current_task,),
            ).fetchall()
        total = sum(count for _, count in rows)
        if total == 0:
            return {}
        return {to_task: count / total for to_task, count in rows}

    def _time_of_day_scores(self, hour: int) -> Dict[str, float]:
        lo, hi = hour - _HOUR_WINDOW, hour + _HOUR_WINDOW
        hours = [h % 24 for h in range(lo, hi + 1)]
        placeholders = ",".join("?" * len(hours))
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT task_type, COUNT(*) FROM task_events
                    WHERE hour IN ({placeholders}) GROUP BY task_type""",
                hours,
            ).fetchall()
        total = sum(count for _, count in rows)
        if total == 0:
            return {}
        return {task_type: count / total for task_type, count in rows}

    def _overall_frequency_scores(self) -> Dict[str, float]:
        with self._lock:
            rows = self._conn.execute("SELECT task_type, COUNT(*) FROM task_events GROUP BY task_type").fetchall()
        total = sum(count for _, count in rows)
        if total == 0:
            return {}
        return {task_type: count / total for task_type, count in rows}

    def _categories_for_tasks(self, task_types) -> Dict[str, Optional[str]]:
        task_types = list(task_types)
        if not task_types:
            return {}
        placeholders = ",".join("?" * len(task_types))
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT task_type, category FROM task_events
                    WHERE task_type IN ({placeholders})
                    ORDER BY id DESC""",
                task_types,
            ).fetchall()
        result: Dict[str, Optional[str]] = {}
        for task_type, category in rows:
            if task_type not in result:
                result[task_type] = category
        return result

    @staticmethod
    def _combine(transition_scores: Dict[str, float], time_scores: Dict[str, float]) -> Dict[str, float]:
        if not transition_scores:
            return dict(time_scores)
        if not time_scores:
            return dict(transition_scores)
        keys = set(transition_scores) | set(time_scores)
        return {
            k: _TRANSITION_WEIGHT * transition_scores.get(k, 0.0) + _TIME_OF_DAY_WEIGHT * time_scores.get(k, 0.0)
            for k in keys
        }


def get_next_task_predictor() -> NextTaskPredictor:
    """Process-wide NextTaskPredictor singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = NextTaskPredictor()
    return _instance
