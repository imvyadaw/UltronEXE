"""
Pattern Analyzer (Phase 19.2 - Intent Prediction)
====================================================
Recurring-sequence detection over the *intent* label stream (via
record_intent()), distinct from PHASE_18_9_1_AI_EVOLUTION/LEARN/
from_habit.py, which mines subsequences over raw action strings. This
module works one level up: it doesn't care what actions produced an
intent, only the order intents themselves tend to occur in (e.g.
"planning" -> "coding" -> "communicating" most weekday mornings), so
intent_predictor.py can ask "given the last few intents, what usually
comes next" and goal_predictor.py can ask "is this sequence typical."

Storage: database/intent_prediction.db, table sequence_log - one row
per intent as it's recorded, in order.
"""

import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "intent_prediction.db"

_instance: Optional["PatternAnalyzer"] = None
_instance_lock = threading.Lock()


class PatternAnalyzer:
    """Mines frequent intent n-grams and flags atypical sequences."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS sequence_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intent TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    # -- logging --------------------------------------------------------
    def record_intent(self, intent: str) -> Dict:
        """Append one intent label to the ordered sequence log."""
        if not intent:
            return {"error": "intent required"}
        with self._lock:
            self._conn.execute(
                "INSERT INTO sequence_log (intent, timestamp) VALUES (?, ?)",
                (intent, time.time()),
            )
            self._conn.commit()
        return {"success": True}

    def _full_sequence(self, limit: int = 5000) -> List[str]:
        with self._lock:
            cur = self._conn.execute("SELECT intent FROM sequence_log ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        return [r[0] for r in reversed(rows)]  # chronological order

    # -- pattern mining -----------------------------------------------------
    def common_sequences(
        self, min_length: int = 2, max_length: int = 4, min_occurrences: int = 2, limit: int = 20
    ) -> List[Dict]:
        """Frequent contiguous intent n-grams (length min_length..max_length)
        across the whole recorded history, most frequent first."""
        sequence = self._full_sequence()
        counts: Counter = Counter()
        for n in range(min_length, max_length + 1):
            for i in range(len(sequence) - n + 1):
                gram = tuple(sequence[i : i + n])
                counts[gram] += 1

        results = [
            {"sequence": list(gram), "occurrences": count} for gram, count in counts.items() if count >= min_occurrences
        ]
        results.sort(key=lambda r: (r["occurrences"], len(r["sequence"])), reverse=True)
        return results[:limit]

    def next_likely(self, current_sequence: List[str], top_n: int = 3) -> List[Dict]:
        """Given the last few intents (most recent last), rank the intents
        that have historically followed that same trailing sub-sequence,
        trying the longest matching prefix first and falling back to
        shorter ones if nothing matches."""
        if not current_sequence:
            return []
        history = self._full_sequence()
        for prefix_len in range(min(len(current_sequence), 3), 0, -1):
            prefix = tuple(current_sequence[-prefix_len:])
            followers: Counter = Counter()
            for i in range(len(history) - prefix_len):
                if tuple(history[i : i + prefix_len]) == prefix:
                    followers[history[i + prefix_len]] += 1
            if followers:
                total = sum(followers.values())
                ranked = [
                    {"intent": intent, "score": round(count / total, 4)}
                    for intent, count in followers.most_common(top_n)
                ]
                return ranked
        return []

    def detect_anomaly(self, recent_intents: List[str], rarity_threshold: int = 1) -> Dict:
        """How typical is this trailing sequence historically? Looks at the
        last bigram/trigram in `recent_intents` and reports how many times
        it's occurred before; below rarity_threshold occurrences counts as
        anomalous (a sequence Ultron hasn't really seen this user do)."""
        if len(recent_intents) < 2:
            return {"anomalous": False, "reason": "not enough history to judge"}
        history = self._full_sequence()
        n = min(3, len(recent_intents))
        trailing = tuple(recent_intents[-n:])
        occurrences = sum(1 for i in range(len(history) - n + 1) if tuple(history[i : i + n]) == trailing)
        return {
            "anomalous": occurrences <= rarity_threshold,
            "sequence": list(trailing),
            "occurrences": occurrences,
        }


def get_pattern_analyzer() -> PatternAnalyzer:
    """Process-wide PatternAnalyzer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PatternAnalyzer()
    return _instance
