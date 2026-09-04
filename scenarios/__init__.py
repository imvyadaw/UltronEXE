"""
Scenarios package (Phase 16)
=============================
Pre-built proactive "routines" - multi-step sequences that go beyond a
single-line alert (proactive/triggers/*.py + proactive/personality/)
into actually gathering information and composing a real briefing:
weather, calendar, system health, pending tasks. Each scenario is a
small class with a `run()` -> Dict (structured result) and a
`briefing_text()` -> str (the ULTRON-voiced version, via
conversation/response_builder.py), so proactive/engine.py's scenario
handlers can call one and speak the result, while other callers (a
voice command like "give me my morning briefing") can call `run()`
directly for the structured data.

    morning_routine.py    - weather + today's calendar + system health
    work_monitor.py        - periodic check-ins during work hours
    meeting_assistant.py   - pre/during/post meeting nudges
    evening_summary.py     - end-of-day wrap-up
"""

from scenarios.morning_routine import MorningRoutine, get_morning_routine
from scenarios.work_monitor import WorkMonitor, get_work_monitor
from scenarios.meeting_assistant import MeetingAssistant, get_meeting_assistant
from scenarios.evening_summary import EveningSummary, get_evening_summary

__all__ = [
    "MorningRoutine",
    "get_morning_routine",
    "WorkMonitor",
    "get_work_monitor",
    "MeetingAssistant",
    "get_meeting_assistant",
    "EveningSummary",
    "get_evening_summary",
]


def register_all_with_engine() -> None:
    """Convenience one-liner for main.py/core.assistant to hook every
    built-in scenario up to the proactive engine's time-based slots in one
    call: get_proactive_engine().register_scenario(category, handler) for
    morning_briefing and evening_wrapup. Meeting nudges and work-monitor
    check-ins are polled by their own scenario classes on demand instead
    (see meeting_assistant.py / work_monitor.py docstrings) since they
    aren't fixed-clock-time events."""
    from proactive.engine import get_proactive_engine

    engine = get_proactive_engine()
    engine.register_scenario("morning_briefing", lambda: get_morning_routine().briefing_text())
    engine.register_scenario("evening_wrapup", lambda: get_evening_summary().briefing_text())
