"""
Predictor (Phase 25 - Proactive Automation)
============================================
Turns "what has Ultron seen the user do before" into "what is the user
about to want". This is the layer beneath proactive/suggester.py - the
suggester decides whether/how to say something, this module only
answers "what does history say is likely right now".

Two prediction strategies, merged:
  - time pattern   - what action is usually observed around this exact
                      time of day + day of week (a 30-minute bucket, so
                      "opens VS Code ~10AM on weekdays" fires whether
                      it's 9:50 or 10:15).
  - sequence chain  - given the most recently observed action, what
                      action has historically followed it most often
                      (a first-order Markov chain over observed
                      actions) - e.g. "opens Outlook" is usually
                      followed by "opens Teams".

Learning is passive and automatic: __init__ subscribes to
core.event_bus's "action.completed" event, so *every* action that goes
through core/action_pipeline.py (voice/text commands, autonomous_engine,
workflow_engine, and this same phase's automatic_actions.py) is
observed without any caller needing to remember to call observe()
directly. observe() is still public for callers that want to feed in
something that didn't go through the pipeline (e.g. proactive/triggers
events).

Storage: database/proactive_predictor.db (own file, same directory as
intelligence/proactive_intelligence's proactive_intelligence.db -
kept separate because this is a different, simpler schema owned by a
different package). Two tables:
  observations      - one row per observed action, with a time-bucket
                       and weekday already computed at insert-time so
                       predict_next() aggregates with plain SQL, no
                       Python-side date math per query.
  sequence_counts    - denormalized (prev_action, next_action) -> count
                       running total, updated on every observe() so
                       predict_next() doesn't need to replay the whole
                       observations table.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.proactive.predictor")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "proactive_predictor.db"

# time-of-day pattern is bucketed to the half hour - fine enough to be
# useful ("around 10AM"), coarse enough that a pattern doesn't need an
# implausible number of exactly-on-the-minute repeats to be detected
TIME_BUCKET_MINUTES = 30
# how many times a (weekday, bucket, action) or (prev, next) pair must
# have been observed before it's confident enough to predict on - one
# or two coincidences shouldn't drive a suggestion
MIN_OBSERVATIONS = 3
# only look at history this recent for time-pattern matching, so a
# routine the user dropped months ago quietly stops being predicted
# instead of haunting them forever
HISTORY_WINDOW_DAYS = 60


class ActionPredictor:
    """Learns action patterns from core.event_bus and answers
    predict_next() / predict_routine() for proactive/suggester.py."""

    def __init__(self, db_path: Path = DB_PATH, auto_subscribe: bool = True):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_name TEXT NOT NULL,
                category TEXT,
                weekday INTEGER,
                time_bucket INTEGER,
                timestamp REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS sequence_counts (
                prev_action TEXT NOT NULL,
                next_action TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                last_seen REAL,
                PRIMARY KEY (prev_action, next_action)
            )""")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_obs_bucket ON observations(weekday, time_bucket, action_name)"
        )
        self._conn.commit()

        self._last_action: Optional[str] = None
        self._subscribed = False
        if auto_subscribe:
            self._subscribe_to_event_bus()

    # -- passive learning ---------------------------------------------------
    def _subscribe_to_event_bus(self) -> None:
        try:
            from core.event_bus import get_event_bus

            bus = get_event_bus()
            bus.subscribe("action.completed", self._on_action_completed)
            self._subscribed = True
            logger.info("Predictor subscribed to core.event_bus 'action.completed'.")
        except Exception as e:
            # Optional wiring - predictor still works via explicit observe()
            # calls even if the event bus import fails for some reason.
            logger.debug(f"Predictor could not subscribe to event bus: {e}")

    def _on_action_completed(self, action: str = "", success: bool = True, **_kwargs) -> None:
        if success and action:
            self.observe(action)

    # -- learning -----------------------------------------------------------
    def observe(self, action_name: str, category: str = "general", when: Optional[float] = None) -> None:
        """Records one occurrence of `action_name`. Safe to call from any
        thread/caller - this is the only write path predict_next() reads from."""
        ts = when if when is not None else time.time()
        local = time.localtime(ts)
        weekday = local.tm_wday  # 0=Monday
        bucket = (local.tm_hour * 60 + local.tm_min) // TIME_BUCKET_MINUTES

        with self._lock:
            self._conn.execute(
                """INSERT INTO observations (action_name, category, weekday, time_bucket, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (action_name, category, weekday, bucket, ts),
            )
            prev = self._last_action
            if prev is not None and prev != action_name:
                self._conn.execute(
                    """INSERT INTO sequence_counts (prev_action, next_action, count, last_seen)
                       VALUES (?, ?, 1, ?)
                       ON CONFLICT(prev_action, next_action)
                       DO UPDATE SET count = count + 1, last_seen = excluded.last_seen""",
                    (prev, action_name, ts),
                )
            self._conn.commit()
            self._last_action = action_name

    # -- prediction -----------------------------------------------------------
    def predict_next(self, context: Optional[Dict] = None, top_k: int = 3) -> List[Dict]:
        """Returns up to `top_k` predictions, each
        {"action_name", "confidence" (0-1), "basis", "observations"},
        merged from the time-pattern and sequence-chain strategies and
        sorted by confidence descending. Empty list means no pattern is
        confident enough yet to predict on."""
        context = context or {}
        now = context.get("timestamp", time.time())
        predictions: Dict[str, Dict] = {}

        for pred in self._predict_by_time(now):
            self._merge_best(predictions, pred)
        for pred in self._predict_by_sequence():
            self._merge_best(predictions, pred)

        ranked = sorted(predictions.values(), key=lambda p: p["confidence"], reverse=True)
        return ranked[:top_k]

    def predict_routine(self, now: Optional[float] = None, min_confidence: float = 0.5) -> Optional[Dict]:
        """Convenience for proactive/engine.py's time-based slot: the single
        highest-confidence time-pattern prediction for right now, or None
        if nothing clears `min_confidence`. Deliberately ignores the
        sequence-chain strategy - a routine slot means "what usually
        happens at this clock time", not "what usually follows the last
        thing that happened"."""
        candidates = self._predict_by_time(now if now is not None else time.time())
        if not candidates:
            return None
        best = max(candidates, key=lambda p: p["confidence"])
        return best if best["confidence"] >= min_confidence else None

    def _predict_by_time(self, timestamp: float) -> List[Dict]:
        local = time.localtime(timestamp)
        weekday = local.tm_wday
        bucket = (local.tm_hour * 60 + local.tm_min) // TIME_BUCKET_MINUTES
        cutoff = timestamp - HISTORY_WINDOW_DAYS * 86400

        with self._lock:
            rows = self._conn.execute(
                """SELECT action_name, COUNT(*) as n FROM observations
                   WHERE weekday = ? AND time_bucket = ? AND timestamp >= ?
                   GROUP BY action_name HAVING n >= ? ORDER BY n DESC""",
                (weekday, bucket, cutoff, MIN_OBSERVATIONS),
            ).fetchall()
            total_row = self._conn.execute(
                """SELECT COUNT(*) FROM observations WHERE weekday = ? AND time_bucket = ? AND timestamp >= ?""",
                (weekday, bucket, cutoff),
            ).fetchone()

        total = total_row[0] if total_row else 0
        if total == 0:
            return []
        return [
            {
                "action_name": name,
                "confidence": round(min(n / total, 1.0), 2),
                "basis": "time_pattern",
                "observations": n,
            }
            for name, n in rows
        ]

    def _predict_by_sequence(self) -> List[Dict]:
        if not self._last_action:
            return []
        with self._lock:
            rows = self._conn.execute(
                """SELECT next_action, count FROM sequence_counts
                   WHERE prev_action = ? AND count >= ? ORDER BY count DESC""",
                (self._last_action, MIN_OBSERVATIONS),
            ).fetchall()
            total_row = self._conn.execute(
                """SELECT SUM(count) FROM sequence_counts WHERE prev_action = ?""",
                (self._last_action,),
            ).fetchone()
        total = total_row[0] if total_row and total_row[0] else 0
        if total == 0:
            return []
        return [
            {
                "action_name": name,
                "confidence": round(min(count / total, 1.0), 2),
                "basis": f"follows '{self._last_action}'",
                "observations": count,
            }
            for name, count in rows
        ]

    @staticmethod
    def _merge_best(predictions: Dict[str, Dict], candidate: Dict) -> None:
        existing = predictions.get(candidate["action_name"])
        if existing is None or candidate["confidence"] > existing["confidence"]:
            predictions[candidate["action_name"]] = candidate

    # -- introspection --------------------------------------------------------
    def history_size(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM observations").fetchone()
        return row[0] if row else 0


_predictor: Optional[ActionPredictor] = None
_predictor_lock = threading.Lock()


def get_action_predictor() -> ActionPredictor:
    """Process-wide singleton, same pattern as proactive.engine.get_proactive_engine()."""
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            _predictor = ActionPredictor()
        return _predictor
