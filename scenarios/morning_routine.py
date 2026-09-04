"""
Morning routine
===============
"Good morning" sequence: weather (skills/internet/weather.py), today's
calendar (skills/calendar/manager.py, which already picks Google vs
Outlook), and a quick system-health read (proactive/monitors/
system_health.py) - Ultron's version of a morning briefing you'd get
from a human assistant. Fired daily by proactive/triggers/time_based.py's
"morning_briefing" slot (see scenarios/__init__.py's
register_all_with_engine()), or callable directly for a voice command
like "give me my morning briefing".

Every data source is optional and fails soft: no calendar configured,
no internet for weather, etc. all just produce a shorter (but still
useful) briefing instead of an error.
"""

from datetime import datetime
from typing import Dict, List, Optional

from skills.internet.weather import WeatherLookup
from skills.calendar.manager import CalendarManager
from proactive.monitors.system_health import get_system_health_monitor
from conversation.response_builder import get_response_builder
from core.logger import get_logger

logger = get_logger("ultron.scenarios.morning_routine")


class MorningRoutine:
    """Gathers weather + today's calendar + system health into one briefing."""

    def __init__(self):
        self._weather = WeatherLookup()
        self._calendar = CalendarManager()
        self._health = get_system_health_monitor()
        self._response_builder = get_response_builder()

    def _gather_weather(self) -> Optional[str]:
        try:
            result = self._weather.get_weather()
            return result.get("weather")
        except Exception as e:
            logger.debug(f"Weather lookup failed: {e}")
            return None

    def _gather_agenda(self) -> List[Dict]:
        try:
            result = self._calendar.execute("daily_agenda")
            if result.get("success"):
                return result.get("events", [])
        except Exception as e:
            logger.debug(f"Calendar lookup failed: {e}")
        return []

    def _gather_health_note(self) -> Optional[str]:
        try:
            snapshot = self._health.snapshot()
            if "error" in snapshot:
                return None
            problems = []
            if snapshot.get("disk_percent", 0) >= 90:
                problems.append(f"disk is at {round(snapshot['disk_percent'])}%")
            battery = snapshot.get("battery")
            if battery and not battery.get("plugged_in", True) and battery.get("percent", 100) < 50:
                problems.append(f"battery is at {round(battery['percent'])}%")
            return "; also, " + ", ".join(problems) if problems else None
        except Exception as e:
            logger.debug(f"Health snapshot failed: {e}")
            return None

    def run(self) -> Dict:
        """Structured briefing data - weather, agenda, health note."""
        return {
            "date": datetime.now().strftime("%A, %B %d"),
            "weather": self._gather_weather(),
            "agenda": self._gather_agenda(),
            "health_note": self._gather_health_note(),
        }

    def briefing_text(self) -> str:
        """The ULTRON-voiced version, ready for proactive.engine to deliver."""
        data = self.run()
        opener = self._response_builder.build_alert("morning_briefing")["text"]

        parts = [opener]
        if data["weather"]:
            parts.append(data["weather"])

        agenda = data["agenda"]
        if agenda:
            titles = [e.get("title", "an event") for e in agenda[:5]]
            if len(titles) == 1:
                parts.append(f"You've got one thing on the calendar today: {titles[0]}.")
            else:
                parts.append(f"You've got {len(agenda)} things on the calendar today, starting with {titles[0]}.")
        else:
            parts.append("Your calendar's clear for today, Sir.")

        if data["health_note"]:
            parts.append(data["health_note"].lstrip("; ").capitalize() + ".")

        return " ".join(parts)


_routine: Optional[MorningRoutine] = None


def get_morning_routine() -> MorningRoutine:
    global _routine
    if _routine is None:
        _routine = MorningRoutine()
    return _routine
