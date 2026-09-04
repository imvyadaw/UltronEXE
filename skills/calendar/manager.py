"""
Calendar skill (Phase 4 facade)
================================
Wraps skills/calendar/scheduler.py - which already auto-picks between
google_calendar.py and outlook_calendar.py - behind the common BaseSkill
interface used by the skill registry / AI tool layer.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.calendar.scheduler import Scheduler


class CalendarManager(BaseSkill):
    """Provider-agnostic scheduling: create, list, reschedule, cancel events."""

    name = "calendar"
    description = "Create, list, reschedule, and cancel calendar events (Google/Outlook), and find free slots."
    category = "productivity"

    def __init__(self, provider: str = "auto"):
        self._scheduler = Scheduler(provider=provider)
        super().__init__()

    def register_actions(self) -> None:
        s = self._scheduler
        self._actions = {
            "schedule": s.schedule_meeting,
            "list_upcoming": s.upcoming_events,
            "cancel": s.cancel_meeting,
            "find_free_slot": s.find_common_free_slot,
            "reschedule": s.reschedule,
            "daily_agenda": s.daily_agenda,
        }

    def health_check(self) -> Dict:
        client = None
        try:
            client = self._scheduler._active_client()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("skills.calendar.manager.health_check")
        return {
            "success": True,
            "skill": self.name,
            "configured": client is not None,
        }
