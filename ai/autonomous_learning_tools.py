"""Autonomous internet-learning tool wiring
============================================
intelligence/ultron_advanced/autonomous_learning.py's scheduler needs a way
for the user to check on it / turn it on or off / ask for a specific topic
right now, without editing .env and restarting. Wired here the same
lazy-handler-dict way as ai/admin_tools.py.

Master ULTRON_LEARN_FROM_INTERNET env flag only controls whether the
scheduler auto-starts at boot (see core/assistant.py) - these tools work
either way, so "start it for me" / "stop learning for now" works in-session
without a restart.
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


def _get_scheduler():
    from intelligence.ultron_advanced.autonomous_learning import get_autonomous_learning_scheduler

    return get_autonomous_learning_scheduler()


def _get_runtime_patcher():
    from self_evolution.runtime_patcher import get_runtime_patcher

    return get_runtime_patcher()


AUTOLEARN_TOOLS = [
    _tool(
        "autolearn_status",
        "Check whether the autonomous internet-learning scheduler is running, what topic "
        "queue it has, how many cycles it has run, and the result of its last cycle.",
    ),
    _tool(
        "autolearn_start",
        "Turn on autonomous internet learning: Ultron will periodically research one topic "
        "(from its curated queue or a stale known fact) and store what it finds into "
        "knowledge_os. Call when the user asks to enable/turn on/start self-learning from "
        "the internet.",
        {
            "interval_hours": {
                "type": "number",
                "description": "Hours between learning cycles. Defaults to 6 if not given.",
            }
        },
    ),
    _tool(
        "autolearn_stop",
        "Turn off autonomous internet learning. Call when the user asks to disable/turn off/"
        "pause self-learning from the internet.",
    ),
    _tool(
        "autolearn_now",
        "Immediately research one topic right now (does not wait for the next scheduled "
        "cycle) and store the findings into knowledge_os. If no topic is given, picks the "
        "next one from the queue the same way a scheduled cycle would.",
        {"topic": {"type": "string", "description": "Specific topic to research now. Optional."}},
    ),
    _tool(
        "autolearn_add_topic",
        "Add a topic to the autonomous learning queue so it gets researched on a future cycle.",
        {"topic": {"type": "string", "description": "Topic to add."}},
        ["topic"],
    ),
    _tool(
        "autolearn_remove_topic",
        "Remove a topic from the autonomous learning queue.",
        {"topic": {"type": "string", "description": "Topic to remove."}},
        ["topic"],
    ),
    _tool(
        "selfheal_code_status",
        "Check the reactive runtime code self-patcher: which repeated tool errors are being "
        "tracked, whether a patch has been auto-applied for any of them, and any recent "
        "patch/rollback actions. Call when the user asks if Ultron has fixed/patched itself, "
        "or wants to know about recent self-healing activity.",
    ),
]

AUTOLEARN_DIRECT_HANDLERS: Dict = {
    "selfheal_code_status": lambda a: _get_runtime_patcher().status(),
    "autolearn_status": lambda a: _get_scheduler().status(),
    "autolearn_start": lambda a: _get_scheduler().start(
        interval_seconds=float(a.get("interval_hours", 6)) * 3600
    ),
    "autolearn_stop": lambda a: _get_scheduler().stop(),
    "autolearn_now": lambda a: _get_scheduler().run_once(topic=a.get("topic") or None),
    "autolearn_add_topic": lambda a: _get_scheduler().add_topic(a.get("topic", "")),
    "autolearn_remove_topic": lambda a: _get_scheduler().remove_topic(a.get("topic", "")),
}
