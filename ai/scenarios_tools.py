r"""
Scenarios tool wiring
========================
scenarios/ (Phase 16) was a fully built, zero-external-references
package - `grep -rn "scenarios\." .` outside scenarios/ itself came
back empty before this file, same dormant-island bug class as
docs/TASK6_DORMANT_AUDIT.md's other 11 packages (that audit flagged
scenarios/ itself as "low-medium risk, out of scope" and left it
unwired; this task wires it - it only reads from already-wired sources
(calendar, weather, system health, task queue), never takes an action).

Each scenario class exposes run() (structured data) and briefing_text()
(the spoken version) except meeting_assistant.check() and
work_monitor.check()/status_text(), which don't need the run()/text
split. register_all_with_engine()/register_with_engine() (the daily-
clock / polling-cadence auto-fire wiring into proactive/engine.py) is
NOT touched here - that's a separate, bigger change (making these fire
on their own schedule) from making them callable on demand ("give me my
morning briefing" right now), which is what this file does.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's _tool() - duplicated on
    purpose (see ai/new_skills_tools.py's docstring for why: avoids a
    circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _get_morning_routine():
    from scenarios.morning_routine import get_morning_routine

    return get_morning_routine()


def _get_evening_summary():
    from scenarios.evening_summary import get_evening_summary

    return get_evening_summary()


def _get_meeting_assistant():
    from scenarios.meeting_assistant import get_meeting_assistant

    return get_meeting_assistant()


def _get_work_monitor():
    from scenarios.work_monitor import get_work_monitor

    return get_work_monitor()


SCENARIOS_TOOLS = [
    _tool(
        "get_morning_briefing",
        "Give the user their morning briefing: weather, today's calendar "
        "agenda, and a system-health note, plus a ready-to-speak summary.",
        {},
    ),
    _tool(
        "get_evening_summary",
        "Give the user their end-of-day wrap-up: how many background tasks "
        "ran today, tomorrow's first calendar item, and a health note, plus "
        "a ready-to-speak summary.",
        {},
    ),
    _tool(
        "check_meeting_reminders",
        "Check upcoming calendar meetings for any that are starting now or "
        "coming up soon and should be flagged to the user.",
        {},
    ),
    _tool(
        "check_work_break_status",
        "Check whether the user has been continuously active long enough "
        "that a break suggestion is due, plus an on-demand 'how am I doing' "
        "status line.",
        {},
    ),
]


SCENARIOS_DIRECT_HANDLERS: Dict = {
    "get_morning_briefing": lambda a: {
        "data": _get_morning_routine().run(),
        "text": _get_morning_routine().briefing_text(),
    },
    "get_evening_summary": lambda a: {
        "data": _get_evening_summary().run(),
        "text": _get_evening_summary().briefing_text(),
    },
    "check_meeting_reminders": lambda a: {"reminders": _get_meeting_assistant().check()},
    "check_work_break_status": lambda a: {
        "break_suggestion": _get_work_monitor().check(),
        "status_text": _get_work_monitor().status_text(),
    },
}
