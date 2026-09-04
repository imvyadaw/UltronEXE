"""
Need Before (PREDICT)
=========================
Time-of-day/day-of-week pattern matching for needs a caller has
recorded before, so a caller can ask "what does this person usually
want around now" rather than needing the person to ask first. Every
recorded need is bucketed by (day-of-week, hour) via record_need();
anticipate() looks up whatever bucket the current (or given) time
falls into and returns needs seen there before, ranked by how often
each has occurred in that slot, historically.

Deliberately coarse (hour-level, not minute-level) buckets - "coffee
most mornings around 7" is the kind of pattern this is for, not exact
timing. A need with only one or two historical occurrences is still
returned (ranked lowest) rather than filtered out, since a caller may
want to lower a confidence threshold itself rather than have this
module silently withhold anything.
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

STATE_FILE_ENV = "AI_EVOLUTION_NEED_BEFORE_FILE"
DEFAULT_STATE_FILE = "data/ai_evolution/need_before.json"


class NeedBefore:
    """Time-bucketed recurring-need lookup. Use get_need_before()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"buckets": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def _bucket_key(self, when: Optional[float] = None) -> str:
        dt = datetime.fromtimestamp(when if when is not None else time.time())
        return f"{dt.weekday()}:{dt.hour}"  # 0=Monday, matching datetime.weekday()

    def record_need(self, need: str, when: Optional[float] = None) -> Dict:
        """Logs `need` as having occurred at `when` (a Unix
        timestamp; defaults to now), bucketed by day-of-week and
        hour. Returns {"success": bool, "error": Optional[str]}."""
        if not need:
            return {"success": False, "error": "need required"}
        data = self._read_state()
        bucket = data["buckets"].setdefault(self._bucket_key(when), {})
        bucket[need] = bucket.get(need, 0) + 1
        self._write_state(data)
        return {"success": True, "error": None}

    def anticipate(self, when: Optional[float] = None, top_n: int = 5) -> List[Tuple[str, int]]:
        """Ranks the `top_n` needs most often recorded in the time
        bucket `when` falls into (defaults to now), by raw
        occurrence count, highest first. Returns an empty list for a
        bucket with no history yet."""
        bucket = self._read_state()["buckets"].get(self._bucket_key(when), {})
        ranked = sorted(bucket.items(), key=lambda pair: pair[1], reverse=True)
        return ranked[:top_n]

    def get_bucket_history(self, when: Optional[float] = None) -> Dict[str, int]:
        """Every need ever recorded in `when`'s time bucket, mapped
        to its raw occurrence count, unranked and unfiltered."""
        return dict(self._read_state()["buckets"].get(self._bucket_key(when), {}))


_need_before: Optional[NeedBefore] = None


def get_need_before() -> NeedBefore:
    global _need_before
    if _need_before is None:
        _need_before = NeedBefore()
    return _need_before
