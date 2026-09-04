"""
From Habit (LEARN)
======================
Recurring-sequence detection over a caller-fed action log, distinct
from PREDICT/next_action.py's single-step transition counts: this
looks for whole repeated subsequences of a configurable length
(a "habit" is N actions in the same order, seen at least
MIN_OCCURRENCES times), the kind of pattern "check weather, then
start coffee maker" that a single-step Markov model would only see as
two separate transitions. record_action() appends to a rolling log;
detect_habits() scans it for repeats.

Sequence length is fixed per call to detect_habits() (its
`sequence_length` argument) rather than this module trying to find
every possible pattern length at once - a caller wanting both 2-step
and 3-step habits calls it twice. Detection is a plain sliding-window
count over the stored log, intentionally simple and re-run-from-
scratch each call rather than maintained incrementally, since the log
is capped at MAX_LOG_SIZE and this stays cheap even so.
"""

import json
import os
import time
from collections import Counter
from typing import Dict, List, Optional

STATE_FILE_ENV = "AI_EVOLUTION_HABITS_FILE"
DEFAULT_STATE_FILE = "data/ai_evolution/habits.json"
MAX_LOG_SIZE = 2000
MIN_OCCURRENCES = 3


class FromHabit:
    """Recurring action-sequence detection. Use get_from_habit()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"log": []}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def record_action(self, action: str) -> Dict:
        """Appends `action` to the rolling log, trimmed to
        MAX_LOG_SIZE most recent entries. Returns {"success": bool,
        "error": Optional[str]}."""
        if not action:
            return {"success": False, "error": "action required"}
        data = self._read_state()
        data["log"] = (data["log"] + [{"action": action, "timestamp": time.time()}])[-MAX_LOG_SIZE:]
        self._write_state(data)
        return {"success": True, "error": None}

    def detect_habits(self, sequence_length: int = 2, min_occurrences: int = MIN_OCCURRENCES) -> List[Dict]:
        """Scans the logged action sequence for every subsequence of
        `sequence_length` consecutive actions occurring at least
        `min_occurrences` times, ranked by occurrence count, highest
        first. Returns a list of {"sequence": Tuple[str, ...],
        "occurrences": int} - empty if the log is shorter than
        `sequence_length` or nothing repeats enough."""
        actions = [entry["action"] for entry in self._read_state()["log"]]
        if len(actions) < sequence_length:
            return []
        counts: Counter = Counter(
            tuple(actions[i : i + sequence_length]) for i in range(len(actions) - sequence_length + 1)
        )
        habits = [
            {"sequence": list(sequence), "occurrences": count}
            for sequence, count in counts.items()
            if count >= min_occurrences
        ]
        habits.sort(key=lambda h: h["occurrences"], reverse=True)
        return habits

    def get_log(self, limit: int = 50) -> List[Dict]:
        """Up to `limit` most recently recorded actions, oldest
        first."""
        return self._read_state()["log"][-limit:]


_from_habit: Optional[FromHabit] = None


def get_from_habit() -> FromHabit:
    global _from_habit
    if _from_habit is None:
        _from_habit = FromHabit()
    return _from_habit
