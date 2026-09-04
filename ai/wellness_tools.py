"""Wellness tracking tool wiring
=================================
Exposes wellness/ (activity_tracker, goal_manager, streak_tracker,
insights_engine) as tools, wired the same lazy-handler-dict way as
ai/finance_tools.py and ai/autonomous_learning_tools.py.

No background scheduler here (unlike finance's market_watcher) - every
tool is a plain local read/write, so there's nothing to gate in
core/assistant.py.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
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


def _get_activity():
    from wellness.activity_tracker import get_activity_tracker

    return get_activity_tracker()


def _get_goals():
    from wellness.goal_manager import get_goal_manager

    return get_goal_manager()


def _get_streaks():
    from wellness.streak_tracker import get_streak_tracker

    return get_streak_tracker()


def _get_insights():
    from wellness.insights_engine import get_wellness_insights_engine

    return get_wellness_insights_engine()


WELLNESS_TOOLS = [
    _tool(
        "log_steps",
        "Log a step count for today (or a given date). Call when the user mentions steps walked.",
        {
            "count": {"type": "integer", "description": "Number of steps."},
            "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Optional, defaults to today."},
        },
        ["count"],
    ),
    _tool(
        "log_water",
        "Log water intake in milliliters. Call when the user mentions drinking water.",
        {
            "ml": {"type": "number", "description": "Amount of water in ml."},
            "date": {"type": "string", "description": "ISO date. Optional, defaults to today."},
        },
        ["ml"],
    ),
    _tool(
        "log_sleep",
        "Log hours slept. Call when the user mentions how much they slept.",
        {
            "hours": {"type": "number", "description": "Hours slept (0-24)."},
            "date": {"type": "string", "description": "ISO date. Optional, defaults to today."},
        },
        ["hours"],
    ),
    _tool(
        "log_workout",
        "Log a workout/exercise session. Call when the user mentions exercising.",
        {
            "workout_type": {"type": "string", "description": "e.g. running, gym, yoga, cycling."},
            "duration_min": {"type": "number", "description": "Duration in minutes."},
            "notes": {"type": "string", "description": "Optional notes."},
            "date": {"type": "string", "description": "ISO date. Optional, defaults to today."},
        },
        ["workout_type", "duration_min"],
    ),
    _tool(
        "log_mood",
        "Log a quick mood check-in on a 1-5 scale (1=low, 5=great). Call when the user shares how "
        "they're feeling in a simple, self-rated way.",
        {
            "score": {"type": "integer", "description": "Mood score 1-5."},
            "note": {"type": "string", "description": "Optional short note."},
            "date": {"type": "string", "description": "ISO date. Optional, defaults to today."},
        },
        ["score"],
    ),
    _tool(
        "wellness_goal_set",
        "Set a personal daily/weekly wellness target the user chooses themselves. Valid metrics: "
        "steps, water_ml, sleep_hours, workouts_weekly.",
        {
            "metric": {"type": "string", "description": "steps | water_ml | sleep_hours | workouts_weekly"},
            "target": {"type": "number", "description": "Target value the user wants to hit."},
        },
        ["metric", "target"],
    ),
    _tool(
        "wellness_status",
        "Check today's activity against every goal the user has set, plus current streaks. Call for "
        "'aaj ka progress kaisa hai' / 'am I hitting my goals' style requests.",
    ),
    _tool(
        "wellness_insights",
        "Generate a combined wellness report (today + this week + goal progress + streaks), with a "
        "short encouraging plain-language narration when possible.",
    ),
]

WELLNESS_DIRECT_HANDLERS: Dict = {
    "log_steps": lambda a: _get_activity().log_steps(a.get("count"), a.get("date")),
    "log_water": lambda a: _get_activity().log_water(a.get("ml"), a.get("date")),
    "log_sleep": lambda a: _get_activity().log_sleep(a.get("hours"), a.get("date")),
    "log_workout": lambda a: _get_activity().log_workout(
        a.get("workout_type", ""), a.get("duration_min"), a.get("notes", ""), a.get("date")
    ),
    "log_mood": lambda a: _get_activity().log_mood(a.get("score"), a.get("note", ""), a.get("date")),
    "wellness_goal_set": lambda a: _get_goals().set_goal(a.get("metric", ""), a.get("target")),
    "wellness_status": lambda a: {
        "goals": _get_goals().get_status(),
        "streaks": _get_streaks().get_streaks(),
    },
    "wellness_insights": lambda a: _get_insights().generate_report(),
}
