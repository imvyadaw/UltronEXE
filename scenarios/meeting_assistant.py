"""
Meeting assistant
=================
Pre/during/post meeting nudges on top of skills/calendar/manager.py's
provider-agnostic calendar (Google/Outlook, already resolved by
skills/calendar/scheduler.py). Polled on a cadence (e.g. every minute
via core/scheduler.py's schedule_every, or from proactive/engine.py -
see register_with_engine() below) rather than reacting to a push
notification, since neither calendar backend here exposes webhooks -
polling upcoming_events() every so often is the simplest thing that
works.

State (which meetings have already been nudged for which stage) is
kept in memory only, keyed by event id + stage - restarting Ultron
mid-meeting means, at worst, one duplicate nudge, which is a much
smaller problem than missing a meeting reminder entirely.
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from skills.calendar.manager import CalendarManager
from conversation.response_builder import get_response_builder
from core.logger import get_logger

logger = get_logger("ultron.scenarios.meeting_assistant")

UPCOMING_WARNING_MINUTES = 10  # nudge this many minutes before start
STARTING_WINDOW_SECONDS = 60  # "starting now" fires within this window of start time


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


class MeetingAssistant:
    """Polls upcoming calendar events and fires pre-meeting / meeting-starting
    nudges exactly once per meeting per stage."""

    def __init__(self):
        self._calendar = CalendarManager()
        self._response_builder = get_response_builder()
        self._nudged_upcoming: Set[str] = set()
        self._nudged_starting: Set[str] = set()

    def _upcoming_events(self) -> List[Dict]:
        try:
            result = self._calendar.execute("list_upcoming", max_results=15)
            if not result.get("success"):
                return []
            return result.get("events", [])
        except Exception as e:
            logger.debug(f"Calendar lookup failed: {e}")
            return []

    def check(self) -> List[Dict]:
        """Returns due events as [{"category": ..., "kwargs": {...}}], meant
        to be handled the same way proactive/triggers/*.py events are -
        via conversation/response_builder.py + ui.notifications."""
        events: List[Dict] = []
        now = datetime.now(timezone.utc)

        for meeting in self._upcoming_events():
            event_id = meeting.get("id") or meeting.get("title", "")
            start = _parse_iso(meeting.get("start", ""))
            if not start or not event_id:
                continue

            minutes_until = (start - now).total_seconds() / 60
            title = meeting.get("title", "your meeting")

            if event_id not in self._nudged_starting and -1 <= minutes_until <= (STARTING_WINDOW_SECONDS / 60):
                self._nudged_starting.add(event_id)
                events.append({"category": "meeting_starting", "kwargs": {"title": title}})
                continue

            if event_id not in self._nudged_upcoming and 0 < minutes_until <= UPCOMING_WARNING_MINUTES:
                self._nudged_upcoming.add(event_id)
                events.append(
                    {
                        "category": "meeting_upcoming",
                        "kwargs": {"title": title, "minutes": round(minutes_until)},
                    }
                )

        return events

    def register_with_engine(self, poll_seconds: float = 60.0) -> None:
        """Starts a background daemon thread that calls check() every
        poll_seconds and delivers any due events via ui.notifications, the
        same way proactive.engine delivers its own events. Not built on
        core.scheduler.Scheduler because that scheduler runs *tool calls*
        by name (core/executor.py) - meeting polling is plain Python, not
        a tool - so a simple dedicated thread is the more direct fit, same
        approach proactive/engine.py itself uses. Optional - call this once
        at startup if meeting nudges are wanted; Ultron works fine without it."""
        import threading
        from ui.notifications import notify

        def _poll_loop():
            while True:
                try:
                    for event in self.check():
                        phrase = self._response_builder.build_alert(event["category"], **event["kwargs"])
                        notify(
                            title="Ultron",
                            message=phrase["text"],
                            level=phrase["level"],
                            source=f"meeting.{event['category']}",
                        )
                except Exception as e:
                    logger.error(f"Meeting assistant poll failed: {e}")
                time.sleep(poll_seconds)

        threading.Thread(target=_poll_loop, daemon=True, name="meeting-assistant").start()


_assistant: Optional[MeetingAssistant] = None


def get_meeting_assistant() -> MeetingAssistant:
    global _assistant
    if _assistant is None:
        _assistant = MeetingAssistant()
    return _assistant
