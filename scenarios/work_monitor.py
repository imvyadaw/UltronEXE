"""
Work monitor
============
Lightweight "how's the work session going" check-in: combines
proactive/monitors/user_activity.py's idle time with
proactive/monitors/system_health.py's CPU reading to suggest a break
after a long unbroken stretch of activity, and stays quiet if the user
already stepped away (idle) or it's outside configured work hours.

Unlike morning_routine.py/evening_summary.py this isn't a fixed daily
clock slot - it's meant to be polled periodically during the day, e.g.
by wiring it into proactive/engine.py's scenario handlers via a
proactive/triggers/time_based.py TimeSlot added every N minutes, or by
calling should_check_in() from a voice command handler.
"""

import time
from typing import Dict, Optional

from proactive.monitors.system_health import get_system_health_monitor
from proactive.monitors.user_activity import get_user_activity_monitor
from conversation.response_builder import get_response_builder
from core.logger import get_logger

logger = get_logger("ultron.scenarios.work_monitor")

DEFAULT_WORK_START_HOUR = 9
DEFAULT_WORK_END_HOUR = 19
CONTINUOUS_ACTIVITY_THRESHOLD_SECONDS = 90 * 60  # suggest a break after 90 min unbroken
IDLE_RESETS_ACTIVITY_SECONDS = 5 * 60  # 5+ min idle counts as "took a break already"
MIN_SECONDS_BETWEEN_SUGGESTIONS = 45 * 60


class WorkMonitor:
    """Tracks how long the user has been continuously active and suggests
    a break during configured work hours."""

    def __init__(self, work_start_hour: int = DEFAULT_WORK_START_HOUR, work_end_hour: int = DEFAULT_WORK_END_HOUR):
        self._health = get_system_health_monitor()
        self._activity = get_user_activity_monitor()
        self._response_builder = get_response_builder()
        self._work_start_hour = work_start_hour
        self._work_end_hour = work_end_hour

        self._activity_started_at: Optional[float] = None
        self._last_suggestion_at: float = 0.0

    def _within_work_hours(self) -> bool:
        hour = time.localtime().tm_hour
        return self._work_start_hour <= hour < self._work_end_hour

    def _update_activity_streak(self) -> Optional[float]:
        """Returns continuous-activity seconds, resetting the streak if the
        user has been idle long enough to count as a break already taken."""
        idle = self._activity.idle_seconds()
        now = time.time()

        if idle is not None and idle >= IDLE_RESETS_ACTIVITY_SECONDS:
            self._activity_started_at = None
            return None

        if self._activity_started_at is None:
            self._activity_started_at = now
            return 0.0

        return now - self._activity_started_at

    def should_check_in(self) -> bool:
        """True if it's a reasonable moment to say something (work hours,
        not already idle, not too soon after the last suggestion)."""
        if not self._within_work_hours():
            return False
        if time.time() - self._last_suggestion_at < MIN_SECONDS_BETWEEN_SUGGESTIONS:
            return False
        return True

    def check(self) -> Optional[Dict]:
        """Returns a {"category": "idle_break_suggestion", "kwargs": {...}}
        event if a break suggestion is due right now, else None. Safe to
        call on any cadence - internally rate-limited."""
        streak_seconds = self._update_activity_streak()
        if streak_seconds is None or not self.should_check_in():
            return None
        if streak_seconds < CONTINUOUS_ACTIVITY_THRESHOLD_SECONDS:
            return None

        self._last_suggestion_at = time.time()
        return {"category": "idle_break_suggestion", "kwargs": {"minutes": round(streak_seconds / 60)}}

    def status_text(self) -> str:
        """On-demand structured-ish status, e.g. for a voice command like
        'how am I doing today' - not tied to the break-suggestion cooldown."""
        try:
            snapshot = self._health.snapshot()
            cpu = snapshot.get("cpu_percent")
            if cpu is None:
                return self._response_builder.build_alert("general_positive")["text"]
            if cpu >= 80:
                return self._response_builder.build_alert("cpu_high", percent=round(cpu))["text"]
            return self._response_builder.build_alert("general_positive")["text"]
        except Exception as e:
            logger.debug(f"Work monitor status failed: {e}")
            return "Everything looks fine, Sir."


_monitor: Optional[WorkMonitor] = None


def get_work_monitor() -> WorkMonitor:
    global _monitor
    if _monitor is None:
        _monitor = WorkMonitor()
    return _monitor
