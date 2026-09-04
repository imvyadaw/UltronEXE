"""
Time-based triggers
====================
Fixed-clock-time proactive events - "9AM briefing", "6PM wrap-up" - the
kind of thing core/scheduler.py *could* run as a one-off `schedule_at`,
but these need to survive process restarts and skip a day cleanly if
Ultron wasn't running at 9AM (rather than firing a stale briefing at
11AM when the process finally starts). So instead this is a simple
"has today's slot already fired" check, polled by proactive/engine.py's
loop (every POLL_INTERVAL_SECONDS, see engine.py) - much simpler than
wiring real cron-style scheduling, and the once-a-day granularity here
doesn't need anything fancier.

Fired state persists via core.state_manager (same JSON-under-storage/
mechanism core/task_queue.py and core/workflow_engine.py already use),
keyed by category + date, so a restart mid-morning doesn't re-fire a
briefing that already went out an hour ago.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from core.state_manager import get_state_manager
from core.logger import get_logger

logger = get_logger("ultron.proactive.time_based")

STATE_KEY_PREFIX = "proactive.time_based.last_fired"


@dataclass
class TimeSlot:
    category: str
    hour: int
    minute: int = 0
    # How many minutes past the slot Ultron will still fire it if it
    # missed the exact minute (process was busy, clock tick was late).
    grace_minutes: int = 30


# Default daily schedule. Scenarios (scenarios/morning_routine.py,
# scenarios/evening_summary.py) are what actually run when these fire -
# this module only decides *when*, not what to say or do.
DEFAULT_SLOTS: List[TimeSlot] = [
    TimeSlot(category="morning_briefing", hour=9, minute=0),
    TimeSlot(category="evening_wrapup", hour=18, minute=0),
]


class TimeBasedTriggers:
    """Polls the wall clock against a list of daily TimeSlots."""

    def __init__(self, slots: Optional[List[TimeSlot]] = None):
        self._slots = slots if slots is not None else list(DEFAULT_SLOTS)
        self._state = get_state_manager()

    def _state_key(self, category: str, day: str) -> str:
        return f"{STATE_KEY_PREFIX}.{category}.{day}"

    def _already_fired_today(self, category: str, day: str) -> bool:
        return bool(self._state.get(self._state_key(category, day), False))

    def _mark_fired(self, category: str, day: str) -> None:
        self._state.set(self._state_key(category, day), True)

    def check(self, now: Optional[datetime] = None) -> List[Dict]:
        """Returns due slots as [{"category": ..., "kwargs": {}}], each fired
        at most once per calendar day. Call this on every engine tick -
        it's cheap (no I/O beyond the already-cached state manager)."""
        now = now or datetime.now()
        day = now.strftime("%Y-%m-%d")
        due: List[Dict] = []

        for slot in self._slots:
            if self._already_fired_today(slot.category, day):
                continue
            slot_time = now.replace(hour=slot.hour, minute=slot.minute, second=0, microsecond=0)
            minutes_past = (now - slot_time).total_seconds() / 60
            if 0 <= minutes_past <= slot.grace_minutes:
                self._mark_fired(slot.category, day)
                due.append({"category": slot.category, "kwargs": {}})

        return due

    def add_slot(self, category: str, hour: int, minute: int = 0, grace_minutes: int = 30) -> None:
        """Register an additional daily slot at runtime (e.g. a user-configured
        custom briefing time), without needing to edit DEFAULT_SLOTS."""
        self._slots.append(TimeSlot(category=category, hour=hour, minute=minute, grace_minutes=grace_minutes))


_triggers: Optional[TimeBasedTriggers] = None


def get_time_based_triggers() -> TimeBasedTriggers:
    global _triggers
    if _triggers is None:
        _triggers = TimeBasedTriggers()
    return _triggers
