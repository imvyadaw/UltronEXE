"""
Evening summary
================
End-of-day wrap-up: how many background tasks ran today
(core/task_queue.py), how the machine's holding up
(proactive/monitors/system_health.py), and tomorrow's first calendar
item if there is one (skills/calendar/manager.py) - the "how did today
go, and what's first tomorrow" that closes out the day. Fired daily by
proactive/triggers/time_based.py's "evening_wrapup" slot (see
scenarios/__init__.py's register_all_with_engine()), or callable
directly for a voice command like "how'd today go".
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

from core.task_queue import get_task_queue
from skills.calendar.manager import CalendarManager
from proactive.monitors.system_health import get_system_health_monitor
from conversation.response_builder import get_response_builder
from core.logger import get_logger

logger = get_logger("ultron.scenarios.evening_summary")


class EveningSummary:
    """Gathers today's completed background tasks + tomorrow's first
    calendar item + a system-health note into one wrap-up."""

    def __init__(self):
        self._task_queue = get_task_queue()
        self._calendar = CalendarManager()
        self._health = get_system_health_monitor()
        self._response_builder = get_response_builder()

    def _gather_task_counts(self) -> Dict:
        try:
            result = self._task_queue.list_tasks(limit=200)
            tasks = result.get("tasks", []) if isinstance(result, dict) else []
            completed = sum(1 for t in tasks if t.get("status") == "completed")
            failed = sum(1 for t in tasks if t.get("status") == "failed")
            return {"completed": completed, "failed": failed, "total": len(tasks)}
        except Exception as e:
            logger.debug(f"Task queue summary failed: {e}")
            return {"completed": 0, "failed": 0, "total": 0}

    def _gather_tomorrow_first_event(self) -> Optional[str]:
        try:
            result = self._calendar.execute("list_upcoming", max_results=10)
            if not result.get("success"):
                return None
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            for event in result.get("events", []):
                if event.get("start", "")[:10] == tomorrow:
                    return event.get("title", "an event")
        except Exception as e:
            logger.debug(f"Calendar lookup failed: {e}")
        return None

    def _gather_health_note(self) -> Optional[str]:
        try:
            snapshot = self._health.snapshot()
            if "error" in snapshot:
                return None
            battery = snapshot.get("battery")
            if battery and not battery.get("plugged_in", True) and battery.get("percent", 100) < 30:
                return f"battery's at {round(battery['percent'])}% - might want to charge overnight"
            return None
        except Exception as e:
            logger.debug(f"Health snapshot failed: {e}")
            return None

    def run(self) -> Dict:
        return {
            "tasks": self._gather_task_counts(),
            "tomorrow_first_event": self._gather_tomorrow_first_event(),
            "health_note": self._gather_health_note(),
        }

    def briefing_text(self) -> str:
        data = self.run()
        opener = self._response_builder.build_alert("evening_wrapup")["text"]
        parts = [opener]

        tasks = data["tasks"]
        if tasks["total"]:
            note = f"{tasks['completed']} background task{'s' if tasks['completed'] != 1 else ''} completed today"
            if tasks["failed"]:
                note += f", {tasks['failed']} didn't make it"
            parts.append(note + ".")

        if data["tomorrow_first_event"]:
            parts.append(f"First thing tomorrow: {data['tomorrow_first_event']}.")

        if data["health_note"]:
            parts.append(data["health_note"].capitalize() + ".")

        parts.append("Rest well, Sir.")
        return " ".join(parts)


_summary: Optional[EveningSummary] = None


def get_evening_summary() -> EveningSummary:
    global _summary
    if _summary is None:
        _summary = EveningSummary()
    return _summary
