"""
From Feedback (LEARN)
=========================
Explicit like/dislike style feedback tracking per `item_id` (a
response template name, a routine name, anything a caller wants
rated), distinct from from_mistake.py's corrected-pairs log: this is
for a caller that already knows what happened and just got a
thumbs-up/down on it, not a "here's what should have happened
instead" correction. record_feedback() appends a signed rating;
get_score() aggregates.

A running score alone can't distinguish "10 people liked it once"
from "one person rated it 10 times," so get_score() also reports the
raw count alongside the aggregate - a caller wanting to weight by
sample size can do that itself rather than this module guessing at a
confidence adjustment.
"""

import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "AI_EVOLUTION_FEEDBACK_FILE"
DEFAULT_STATE_FILE = "data/ai_evolution/feedback.json"
MAX_RATINGS_PER_ITEM = 200


class FromFeedback:
    """Per-item feedback aggregation. Use get_from_feedback()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"items": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def record_feedback(self, item_id: str, rating: int, comment: Optional[str] = None) -> Dict:
        """Logs `rating` (any int; a caller might use -1/+1 or a
        1-5 scale, this module doesn't enforce a range) for
        `item_id`, trimmed to MAX_RATINGS_PER_ITEM most recent
        ratings. Returns {"success": bool, "error": Optional[str]}."""
        if not item_id:
            return {"success": False, "error": "item_id required"}
        data = self._read_state()
        ratings = data["items"].setdefault(item_id, [])
        ratings.append({"rating": rating, "comment": comment, "timestamp": time.time()})
        data["items"][item_id] = ratings[-MAX_RATINGS_PER_ITEM:]
        self._write_state(data)
        return {"success": True, "error": None}

    def get_score(self, item_id: str) -> Dict:
        """Aggregate feedback for `item_id`. Returns {"average":
        Optional[float], "count": int, "total": int} - "average" is
        None (not 0.0) when `count` is zero, so a caller can tell "no
        feedback yet" apart from "feedback averaged to zero"."""
        ratings = [r["rating"] for r in self._read_state()["items"].get(item_id, [])]
        if not ratings:
            return {"average": None, "count": 0, "total": 0}
        return {"average": round(sum(ratings) / len(ratings), 3), "count": len(ratings), "total": sum(ratings)}

    def get_history(self, item_id: str, limit: int = 20) -> List[Dict]:
        """Up to `limit` most recent ratings for `item_id`, oldest
        first."""
        return self._read_state()["items"].get(item_id, [])[-limit:]

    def list_items(self) -> List[str]:
        """IDs of every item ever rated."""
        return list(self._read_state()["items"].keys())


_from_feedback: Optional[FromFeedback] = None


def get_from_feedback() -> FromFeedback:
    global _from_feedback
    if _from_feedback is None:
        _from_feedback = FromFeedback()
    return _from_feedback
