"""
Next Action (PREDICT)
=========================
A first-order Markov chain over whatever action names a caller feeds
it via record(): every action is logged after the one before it, and
predict() ranks candidates purely by how often each followed the
current action historically. No ML library, no black box - it's
transaction counts under data/ai_evolution/next_action.json, so
predict()'s ranking is always traceable back to
"X followed Y N times."

Deliberately order-1 only (predicts from the single most recent
action, not a longer sequence) to keep the count table small and the
ranking legible; from_habit.py in LEARN/ is where longer recurring
sequences get detected instead. This module doesn't care what an
"action" string means - "opened_calendar", "turned_on_kitchen_light",
anything a caller wants tracked - it just counts transitions between
whatever strings it's given.
"""

import json
import os
import time
from typing import Dict, List, Optional, Tuple

STATE_FILE_ENV = "AI_EVOLUTION_NEXT_ACTION_FILE"
DEFAULT_STATE_FILE = "data/ai_evolution/next_action.json"
MAX_RECENT_LOG = 500


class NextAction:
    """Order-1 Markov action predictor. Use get_next_action()."""

    def __init__(self):
        self._last_action: Optional[str] = None  # in-memory only; not persisted across restarts

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"transitions": {}, "recent": []}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def record(self, action: str) -> Dict:
        """Logs `action` as having just happened, incrementing the
        transition count from whatever action was recorded
        immediately before it in this process (nothing is counted for
        the very first action recorded after startup, since there's
        no prior action to transition from). Returns {"success":
        bool, "error": Optional[str]}."""
        if not action:
            return {"success": False, "error": "action required"}
        data = self._read_state()
        if self._last_action is not None:
            bucket = data["transitions"].setdefault(self._last_action, {})
            bucket[action] = bucket.get(action, 0) + 1
        data["recent"] = (data.get("recent", []) + [{"action": action, "timestamp": time.time()}])[-MAX_RECENT_LOG:]
        self._write_state(data)
        self._last_action = action
        return {"success": True, "error": None}

    def predict(self, current_action: Optional[str] = None, top_n: int = 3) -> List[Tuple[str, int]]:
        """Ranks the `top_n` actions most likely to follow
        `current_action` (or the last action recorded in this process
        if omitted), by raw historical transition count, highest
        first. Returns an empty list if there's no history for that
        action yet - never guesses."""
        source = current_action if current_action is not None else self._last_action
        if source is None:
            return []
        bucket = self._read_state()["transitions"].get(source, {})
        ranked = sorted(bucket.items(), key=lambda pair: pair[1], reverse=True)
        return ranked[:top_n]

    def get_recent(self, limit: int = 20) -> List[Dict]:
        """Up to `limit` most recently recorded actions, oldest
        first, each as {"action": str, "timestamp": float}."""
        return self._read_state().get("recent", [])[-limit:]

    def reset(self) -> Dict:
        """Clears every transition count and the recent log. Returns
        {"success": bool, "error": Optional[str]}."""
        self._write_state({"transitions": {}, "recent": []})
        self._last_action = None
        return {"success": True, "error": None}


_next_action: Optional[NextAction] = None


def get_next_action() -> NextAction:
    global _next_action
    if _next_action is None:
        _next_action = NextAction()
    return _next_action
