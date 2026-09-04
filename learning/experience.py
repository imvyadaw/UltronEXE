"""
Experience Store (Phase 4.1 - Learning & Safety)
=================================================
The raw memory layer under learning/learner.py. Every time an action
runs to completion (successfully or not), a single Experience row is
recorded here: what was attempted, in what context, what happened, and
how good/bad that outcome was (reward). learner.py is the only normal
caller - it turns event_bus activity into add_experience() calls and
reads the aggregates back out to decide what Ultron should trust.

This is deliberately separate from learn/ (habit-of-the-user mining:
"user always mutes at 9pm") and learning_engine/ (feedback/RL scaffolding
for model behaviour) - both of those are about *predicting the user*.
This module is about *grading Ultron's own actions* so safety/trust_policy.py
has real numbers to work from instead of a static allow-list.

Storage: database/learning_experience.db (own file, same directory as
every other package's db - see proactive/predictor.py for the same
pattern). One table:
  experiences - one row per completed action attempt, with a
                pre-computed reward so aggregate queries (success rate,
                average reward) are plain SQL, no Python-side replay.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.learning.experience")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "learning_experience.db"

# how much history a single get_recent()/stats() call will pull back by
# default - callers that genuinely need more can raise `limit` per call
DEFAULT_LIMIT = 200


def _reward_for(success: bool, explicit_reward: Optional[float]) -> float:
    """Outcome -> a single scalar signal. Callers can always override
    with an explicit reward (e.g. -1.0 for "technically succeeded but
    the user immediately undid it"); this is just the sane default."""
    if explicit_reward is not None:
        return max(-1.0, min(1.0, explicit_reward))
    return 1.0 if success else -1.0


class ExperienceStore:
    """Append-only log of (context, action, outcome, reward) records,
    plus the aggregate reads learner.py needs."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_name TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                success INTEGER NOT NULL,
                reward REAL NOT NULL,
                error TEXT,
                source TEXT NOT NULL DEFAULT 'event_bus',
                created_at REAL NOT NULL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_experiences_action ON experiences(action_name)")
        self._conn.commit()

    def add_experience(
        self,
        action_name: str,
        success: bool,
        context: Optional[Dict] = None,
        reward: Optional[float] = None,
        error: Optional[str] = None,
        source: str = "event_bus",
    ) -> int:
        """Record one completed action attempt. Never raises - a
        logging failure shouldn't take down whatever just finished
        executing; it's logged and 0 is returned instead."""
        row = (
            action_name,
            json.dumps(context or {}, default=str),
            1 if success else 0,
            _reward_for(success, reward),
            error,
            source,
            time.time(),
        )
        try:
            with self._lock:
                cur = self._conn.execute(
                    """INSERT INTO experiences
                       (action_name, context, success, reward, error, source, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
                self._conn.commit()
                return cur.lastrowid
        except Exception as exc:
            logger.error(f"add_experience failed for {action_name}: {exc}")
            return 0

    def get_recent(self, action_name: Optional[str] = None, limit: int = DEFAULT_LIMIT) -> List[Dict]:
        with self._lock:
            if action_name:
                cur = self._conn.execute(
                    """SELECT id, action_name, context, success, reward, error, source, created_at
                       FROM experiences WHERE action_name = ?
                       ORDER BY id DESC LIMIT ?""",
                    (action_name, limit),
                )
            else:
                cur = self._conn.execute(
                    """SELECT id, action_name, context, success, reward, error, source, created_at
                       FROM experiences ORDER BY id DESC LIMIT ?""",
                    (limit,),
                )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "action_name": r[1],
                "context": json.loads(r[2]) if r[2] else {},
                "success": bool(r[3]),
                "reward": r[4],
                "error": r[5],
                "source": r[6],
                "created_at": r[7],
            }
            for r in rows
        ]

    def stats_for(self, action_name: str, window: int = DEFAULT_LIMIT) -> Dict:
        """Aggregate success rate / average reward over the most recent
        `window` attempts of this action. Returns sample_size=0 rather
        than raising when the action has never been observed - callers
        (trust_policy) treat that as "no data, fall back to default"."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT success, reward FROM
                   (SELECT success, reward FROM experiences
                    WHERE action_name = ? ORDER BY id DESC LIMIT ?)""",
                (action_name, window),
            )
            rows = cur.fetchall()
        sample_size = len(rows)
        if sample_size == 0:
            return {"action_name": action_name, "sample_size": 0, "success_rate": None, "avg_reward": None}
        successes = sum(1 for s, _ in rows if s)
        avg_reward = sum(r for _, r in rows) / sample_size
        return {
            "action_name": action_name,
            "sample_size": sample_size,
            "success_rate": successes / sample_size,
            "avg_reward": avg_reward,
        }

    def all_known_actions(self) -> List[str]:
        with self._lock:
            cur = self._conn.execute("SELECT DISTINCT action_name FROM experiences")
            return [r[0] for r in cur.fetchall()]

    def prune_older_than(self, days: int) -> int:
        """Housekeeping - old experiences stop being useful signal and
        just bloat the db. Not called automatically; learner.py or a
        maintenance task can invoke it on a schedule."""
        cutoff = time.time() - (days * 86400)
        with self._lock:
            cur = self._conn.execute("DELETE FROM experiences WHERE created_at < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount


_store: Optional[ExperienceStore] = None
_store_lock = threading.Lock()


def get_experience_store() -> ExperienceStore:
    """Process-wide singleton, same pattern as proactive.predictor.get_action_predictor()."""
    global _store
    with _store_lock:
        if _store is None:
            _store = ExperienceStore()
        return _store
