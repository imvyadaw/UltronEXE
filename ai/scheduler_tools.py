r"""
Scheduler tool wiring
========================
scheduler/background_tasks.py (Phase 30) was fully built but nothing
called it, AND - a level deeper - the two systems it wraps
(core/task_queue.py and core/scheduler.py) had no AI-tool entry either;
`grep -rln "core.scheduler\|core\.task_queue\|schedule_in\|schedule_at\|schedule_every\|get_task_queue" ai/*.py`
came back with zero files before this one. So this wasn't just an
unwired wrapper, it was an unwired *capability* - the model had no way
to say "run this tool in 10 minutes" or "run this every hour" at all.

submit_now() is deliberately NOT wired: it takes a raw Python Callable,
which an AI tool call (JSON args only) can't supply - submit_later/
submit_at/submit_recurring take a tool_name + arguments dict instead,
which is exactly what a tool call already looks like, so those three
are the natural fit.
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


def _get_background_tasks():
    from scheduler.background_tasks import get_background_tasks

    return get_background_tasks()


SCHEDULER_TOOLS = [
    _tool(
        "schedule_tool_in",
        "Schedule a tool call to run once, a number of seconds from now "
        "(e.g. 'remind me in 20 minutes' -> schedule the reminder tool with "
        "seconds=1200).",
        {
            "seconds": {"type": "number"},
            "tool_name": {"type": "string", "description": "Name of the tool to run later"},
            "arguments": {"type": "object", "description": "Arguments to pass to that tool"},
        },
        ["seconds", "tool_name"],
    ),
    _tool(
        "schedule_tool_at",
        "Schedule a tool call to run once at a specific date/time.",
        {
            "when_iso": {"type": "string", "description": "ISO 8601 datetime, e.g. 2026-09-01T09:00:00"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
        },
        ["when_iso", "tool_name"],
    ),
    _tool(
        "schedule_tool_recurring",
        "Schedule a tool call to run repeatedly on a fixed interval.",
        {
            "interval_seconds": {"type": "number"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
        },
        ["interval_seconds", "tool_name"],
    ),
    _tool(
        "get_scheduled_task_status",
        "Check the status of a task previously scheduled with schedule_tool_in/at/recurring.",
        {"task_id": {"type": "string"}},
        ["task_id"],
    ),
    _tool(
        "cancel_scheduled_task",
        "Cancel a previously scheduled task.",
        {"task_id": {"type": "string"}},
        ["task_id"],
    ),
]


SCHEDULER_DIRECT_HANDLERS: Dict = {
    "schedule_tool_in": lambda a: _get_background_tasks().submit_later(
        a.get("seconds", 0), a.get("tool_name", ""), a.get("arguments") or {}
    ),
    "schedule_tool_at": lambda a: _get_background_tasks().submit_at(
        a.get("when_iso", ""), a.get("tool_name", ""), a.get("arguments") or {}
    ),
    "schedule_tool_recurring": lambda a: _get_background_tasks().submit_recurring(
        a.get("interval_seconds", 0), a.get("tool_name", ""), a.get("arguments") or {}
    ),
    "get_scheduled_task_status": lambda a: _get_background_tasks().status(a.get("task_id", "")),
    "cancel_scheduled_task": lambda a: _get_background_tasks().cancel(a.get("task_id", "")),
}
