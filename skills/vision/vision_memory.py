"""
skills/vision/vision_memory.py
================================
Small persistence layer behind change_detector.py: remembers the current
"baseline" frame (what the camera last saw when told to start watching)
and a rolling history of change events, across process restarts.

Deliberately a plain JSON file under storage/cache/ (VISION_MEMORY_FILE
in config.py) rather than a new sqlite table in database/database_manager.py -
matches the existing storage/cache/ultron_state.json /
installed_apps_cache.json convention used elsewhere for small,
single-writer, non-queried state, instead of adding a 10th database file
for one baseline + a capped events list.

No camera/diffing logic lives here - change_detector.py owns that and
only asks this module to persist/retrieve the results.
"""

import json
import os
import threading
import time
from typing import Dict, List, Optional

from config import CHANGE_DETECTION_MAX_EVENTS, CHANGE_DETECTION_MEMORY_FILE


class VisionMemory:
    """Disk-backed baseline + change-event history. Use get_vision_memory()."""

    def __init__(self, path: str = CHANGE_DETECTION_MEMORY_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._state = self._load()

    # -- persistence -----------------------------------------------------
    def _load(self) -> Dict:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("baseline", None)
                    data.setdefault("events", [])
                    return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            from core.error_trace import log_swallowed as _lsw

            _lsw("skills.vision.vision_memory._load")
        return {"baseline": None, "events": []}

    def _save(self) -> None:
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except OSError:
            from core.error_trace import log_swallowed as _lsw

            _lsw("skills.vision.vision_memory._save")

    # -- baseline ----------------------------------------------------------
    def get_baseline(self) -> Optional[Dict]:
        """{"snapshot_path": str, "set_at": float} or None if never set /
        cleared."""
        with self._lock:
            return dict(self._state["baseline"]) if self._state["baseline"] else None

    def set_baseline(self, snapshot_path: str) -> Dict:
        baseline = {"snapshot_path": snapshot_path, "set_at": time.time()}
        with self._lock:
            self._state["baseline"] = baseline
            self._save()
        return dict(baseline)

    def clear_baseline(self) -> None:
        with self._lock:
            self._state["baseline"] = None
            self._save()

    # -- events --------------------------------------------------------------
    def record_event(self, event: Dict) -> Dict:
        """Appends `event` (should already contain change_percent,
        snapshot_path, etc.) with a `detected_at` timestamp, trimmed to
        CHANGE_DETECTION_MAX_EVENTS most recent."""
        event = dict(event)
        event.setdefault("detected_at", time.time())
        with self._lock:
            events: List[Dict] = self._state["events"]
            events.append(event)
            if len(events) > CHANGE_DETECTION_MAX_EVENTS:
                del events[: len(events) - CHANGE_DETECTION_MAX_EVENTS]
            self._save()
        return event

    def get_recent_events(self, limit: int = 10) -> List[Dict]:
        with self._lock:
            events = self._state["events"]
            return list(events[-limit:][::-1])  # most recent first

    def clear_events(self) -> None:
        with self._lock:
            self._state["events"] = []
            self._save()


_memory: Optional[VisionMemory] = None


def get_vision_memory() -> VisionMemory:
    """Process-wide VisionMemory singleton, matching this codebase's
    get_x() convention."""
    global _memory
    if _memory is None:
        _memory = VisionMemory()
    return _memory
