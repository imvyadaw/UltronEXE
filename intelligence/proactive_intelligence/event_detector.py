"""
Event Detector (Phase 20.1 - Proactive Intelligence)
==================================================
Front door for the proactive_intelligence/ package: turns a raw
signal from anywhere else in ULTRON - a calendar reminder firing, a
security alert from ULTRON_SHIELD (Phase 17.9), a download finishing,
a habit-tracker nudge, disk space running low - into one consistent
"detected event" shape the rest of this package can reason about,
and filters out signals that aren't worth surfacing at all (unknown
signal types, or the same thing firing again moments after it was
already detected).

Deliberately simple/heuristic, same spirit as barge_in_detector.py in
Phase 20: a lookup table maps known signal_type values to a category,
a small per-category default title/description fills in whatever the
caller's payload didn't provide, and a short in-memory dedup window
suppresses re-detecting the literal same signal if a caller polls
faster than the underlying condition actually changes. Like
barge_in_detector.py, detect() always returns a dict describing the
decision (never None) so callers get reasons even on a negative
result.

This module only classifies and normalizes - it never decides how
urgent something is (urgency_calculator.py's job), whether now is a
good time to say anything about it (user_disruption_guard.py's job),
or what to actually say (suggestion_generator.py's job).

Dedup state is in-memory only, same spirit as filler_generator.py's
last-index rotation in Phase 20: which signals were recently seen is
only relevant within a single running process and resets harmlessly
on restart. No database table.
"""

import threading
import time
from typing import Dict, Optional

_instance: Optional["EventDetector"] = None
_instance_lock = threading.Lock()

CATEGORY_REMINDER = "reminder"
CATEGORY_DEADLINE = "deadline"
CATEGORY_SYSTEM = "system"
CATEGORY_SECURITY = "security"
CATEGORY_COMMUNICATION = "communication"
CATEGORY_TASK_COMPLETE = "task_complete"
CATEGORY_ROUTINE = "routine"

# known signal_type values this ULTRON build can raise, mapped to the
# category the rest of the package reasons about. Any signal_type not
# in here is treated as not-our-concern rather than guessed at.
_SIGNAL_TYPE_CATEGORY = {
    "calendar_reminder": CATEGORY_REMINDER,
    "task_reminder": CATEGORY_REMINDER,
    "task_due": CATEGORY_DEADLINE,
    "deadline_approaching": CATEGORY_DEADLINE,
    "battery_low": CATEGORY_SYSTEM,
    "disk_space_low": CATEGORY_SYSTEM,
    "update_available": CATEGORY_SYSTEM,
    "system_error": CATEGORY_SYSTEM,
    "intrusion_alert": CATEGORY_SECURITY,
    "suspicious_process": CATEGORY_SECURITY,
    "firewall_block": CATEGORY_SECURITY,
    "new_email": CATEGORY_COMMUNICATION,
    "new_message": CATEGORY_COMMUNICATION,
    "missed_call": CATEGORY_COMMUNICATION,
    "download_complete": CATEGORY_TASK_COMPLETE,
    "long_process_complete": CATEGORY_TASK_COMPLETE,
    "backup_complete": CATEGORY_TASK_COMPLETE,
    "routine_nudge": CATEGORY_ROUTINE,
    "habit_check_in": CATEGORY_ROUTINE,
}

_DEFAULT_TITLES = {
    CATEGORY_REMINDER: "You had a reminder set",
    CATEGORY_DEADLINE: "Something's coming up",
    CATEGORY_SYSTEM: "System notice",
    CATEGORY_SECURITY: "Security alert",
    CATEGORY_COMMUNICATION: "New message",
    CATEGORY_TASK_COMPLETE: "A task just finished",
    CATEGORY_ROUTINE: "Just checking in",
}

# same signal_type+identity firing again inside this window is treated
# as noise, not a new event - callers that poll a condition (e.g.
# "is disk space still low?") every few seconds shouldn't cause a new
# detection every time they poll
_DEDUP_WINDOW_SECONDS = 300.0

# how long entries are kept in the dedup cache before being pruned,
# so a long-running process doesn't grow this dict forever
_DEDUP_CACHE_TTL_SECONDS = 3600.0


class EventDetector:
    """raw_signal -> {"is_event", "event", "reasons"}."""

    def __init__(self):
        self._lock = threading.Lock()
        self._recently_seen: Dict[str, float] = {}

    def detect(self, raw_signal: Dict) -> Dict:
        reasons = []
        signal_type = raw_signal.get("signal_type")
        if not signal_type:
            reasons.append("no signal_type provided")
            return {"is_event": False, "event": None, "reasons": reasons}

        category = _SIGNAL_TYPE_CATEGORY.get(signal_type)
        if category is None:
            reasons.append(f"signal_type '{signal_type}' is not a recognized proactive signal")
            return {"is_event": False, "event": None, "reasons": reasons}

        payload = raw_signal.get("payload") or {}
        signature = self._signature(signal_type, payload)
        now = time.time()
        if self._is_duplicate(signature, now):
            reasons.append(
                f"signal '{signature}' already detected within the last "
                f"{_DEDUP_WINDOW_SECONDS:.0f}s - suppressing as a repeat"
            )
            return {"is_event": False, "event": None, "reasons": reasons}

        title = payload.get("title") or _DEFAULT_TITLES.get(category, "Notice")
        description = payload.get("description") or payload.get("summary") or ""

        event = {
            "event_type": signal_type,
            "category": category,
            "title": title,
            "description": description,
            "payload": payload,
            "source": raw_signal.get("source"),
            "severity_hint": raw_signal.get("severity"),
            "detected_at": now,
        }
        reasons.append(f"signal_type '{signal_type}' recognized as category '{category}'")
        return {"is_event": True, "event": event, "reasons": reasons}

    def _is_duplicate(self, signature: str, now: float) -> bool:
        with self._lock:
            self._prune_locked(now)
            last_seen = self._recently_seen.get(signature)
            self._recently_seen[signature] = now
            return last_seen is not None and (now - last_seen) < _DEDUP_WINDOW_SECONDS

    def _prune_locked(self, now: float) -> None:
        stale = [sig for sig, ts in self._recently_seen.items() if (now - ts) > _DEDUP_CACHE_TTL_SECONDS]
        for sig in stale:
            self._recently_seen.pop(sig, None)

    @staticmethod
    def _signature(signal_type: str, payload: Dict) -> str:
        # prefer a caller-supplied stable id (e.g. the calendar event's
        # own id) so two different reminders of the same signal_type
        # aren't accidentally treated as duplicates of each other
        identity = payload.get("id") or payload.get("title") or ""
        return f"{signal_type}:{identity}"


def get_event_detector() -> EventDetector:
    """Process-wide EventDetector singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EventDetector()
    return _instance
