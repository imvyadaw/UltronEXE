"""
Intent Router
=============
Sits one step further than ai/local_router.py (which only catches mode
toggles and single unambiguous system commands). This module classifies
input into a few *structural* intents that change which subsystem should
own the request, before it falls through to the normal LLM tool-calling
loop:

  - WORKFLOW  - "run <name> workflow" / "run my <name> routine"
                -> core.workflow_engine
  - BACKGROUND - "in the background, ..." / "<task> asynchronously" /
                 "background me ... karo" (Hinglish)
                -> core.task_queue, wrapping the LLM call itself so the
                   voice/text loop doesn't block on a long turn
  - TASK_STATUS - "status of task <id>" / "is task <id> done"
                -> core.task_queue.get_status
  - CHAT      - everything else; caller falls through to Groq/local LLM
                exactly as before.

Deliberately conservative like local_router: only classifies patterns it
is confident about and backs off to CHAT otherwise, since a wrong guess
here would silently change how a command is handled instead of just
answering it slower.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.intent_router")

WORKFLOW_PATTERNS = [
    re.compile(r"^\s*run\s+(?:the\s+)?(?:workflow|routine)\s+(?P<name>.+?)\s*$", re.I),
    re.compile(r"^\s*run\s+(?:my\s+)?(?P<name>.+?)\s+(?:workflow|routine)\s*$", re.I),
    re.compile(r"^\s*start\s+(?P<name>.+?)\s+(?:workflow|routine)\s*$", re.I),
]

BACKGROUND_PATTERNS = [
    re.compile(r"^\s*(?:in\s+the\s+background|background\s*(?:me|mein))[,:]?\s*(?P<goal>.+)$", re.I),
    re.compile(r"^\s*(?P<goal>.+?)\s+(?:in\s+the\s+background|asynchronously|async(?:\s+se|\s+mein)?)\s*$", re.I),
]

TASK_STATUS_PATTERNS = [
    re.compile(r"^\s*(?:what'?s|check)?\s*(?:the\s+)?status\s+of\s+task\s+(?P<task_id>[a-f0-9]+)\s*$", re.I),
    re.compile(r"^\s*is\s+task\s+(?P<task_id>[a-f0-9]+)\s+(?:done|finished|complete)\??\s*$", re.I),
]

LIST_TASKS_PATTERNS = [
    re.compile(r"^\s*(?:list|show)\s+(?:my\s+)?(?:background\s+)?tasks\s*$", re.I),
]


@dataclass
class IntentResult:
    intent: str  # "workflow" | "background" | "task_status" | "list_tasks" | "chat"
    matched: bool = False
    response: Optional[str] = None  # ready-to-speak/print reply, if fully handled here
    handled_locally: bool = False  # True once response is final, caller should not call the LLM
    payload: Dict[str, Any] = field(default_factory=dict)


def _first_match(patterns, text: str):
    cleaned = text.strip()
    for pattern in patterns:
        m = pattern.match(cleaned)
        if m:
            return m
    return None


def classify(text: str) -> IntentResult:
    """Classify `text` without executing anything - cheap, side-effect free."""
    m = _first_match(WORKFLOW_PATTERNS, text)
    if m:
        return IntentResult(intent="workflow", matched=True, payload={"name": m.group("name").strip()})

    m = _first_match(TASK_STATUS_PATTERNS, text)
    if m:
        return IntentResult(intent="task_status", matched=True, payload={"task_id": m.group("task_id").strip()})

    m = _first_match(LIST_TASKS_PATTERNS, text)
    if m:
        return IntentResult(intent="list_tasks", matched=True, payload={})

    m = _first_match(BACKGROUND_PATTERNS, text)
    if m:
        goal = m.group("goal").strip()
        if goal:
            return IntentResult(intent="background", matched=True, payload={"goal": goal})

    return IntentResult(intent="chat", matched=False)


def route(text: str, chat_fn: Optional[Callable[[str], str]] = None) -> IntentResult:
    """Classify `text` and, for intents this router owns end-to-end, also
    execute them and fill in `response`/`handled_locally`.

    `chat_fn` - the normal LLM call (e.g. UltronGroqClient.chat_with_tools),
    used only for the "background" intent, where the goal still needs the
    LLM/tool-calling loop but should run off the main thread.
    """
    # User-registered custom shortcuts (voice/voice_commands.py) win over
    # the built-in patterns below when they confidently match - that's
    # the whole point of letting someone define their own phrase.
    try:
        from voice.voice_commands import get_voice_command_registry

        vc_outcome = get_voice_command_registry().execute_if_matched(text)
    except Exception:
        vc_outcome = None
    if vc_outcome is not None:
        result = IntentResult(intent="voice_command", matched=True, handled_locally=True, payload=vc_outcome)
        inner = vc_outcome.get("result")
        if isinstance(inner, dict) and inner.get("error"):
            result.response = f"Tried '{vc_outcome['matched_phrase']}' but it failed: {inner['error']}"
        else:
            result.response = f"Done ({vc_outcome['matched_phrase']})."
        return result

    result = classify(text)

    if result.intent == "workflow":
        from core.workflow_engine import get_workflow_engine

        engine = get_workflow_engine()
        name = result.payload["name"]
        if "error" in engine.get_workflow(name):
            # Fall back to the simpler, older WorkflowRunner's storage in
            # case the workflow was saved via save_workflow/run_workflow
            # (skills/automation) rather than the advanced engine.
            try:
                from automation.workflow.workflow import WorkflowRunner

                simple = WorkflowRunner()
                if "error" not in simple.get_workflow(name):
                    outcome = simple.run_workflow(name)
                    ok = outcome.get("success", False)
                    result.response = (
                        f"Ran workflow '{name}'."
                        if ok
                        else f"Workflow '{name}' failed at step {outcome.get('failed_at_step')}."
                    )
                    result.handled_locally = True
                    result.payload["result"] = outcome
                    return result
            except Exception as e:
                logger.warning(f"Fallback to simple WorkflowRunner failed: {e}")
            result.response = f"I don't have a workflow named '{name}'."
            result.handled_locally = True
            return result

        outcome = engine.run_workflow(name)
        ok = outcome.get("success", False)
        result.response = (
            f"Ran workflow '{name}' ({len(outcome.get('steps', []))} steps)."
            if ok
            else f"Workflow '{name}' failed at step {outcome.get('failed_at_step')}."
        )
        result.handled_locally = True
        result.payload["result"] = outcome
        return result

    if result.intent == "task_status":
        from core.task_queue import get_task_queue

        status = get_task_queue().get_status(result.payload["task_id"])
        if "error" in status:
            result.response = status["error"]
        else:
            result.response = f"Task '{status['label']}' is {status['status']}."
        result.handled_locally = True
        result.payload["status"] = status
        return result

    if result.intent == "list_tasks":
        from core.task_queue import get_task_queue

        listing = get_task_queue().list_tasks()
        if listing["count"] == 0:
            result.response = "No background tasks yet."
        else:
            names = ", ".join(f"{t['label']} ({t['status']})" for t in listing["tasks"][:5])
            result.response = f"{listing['count']} task(s): {names}"
        result.handled_locally = True
        result.payload["tasks"] = listing
        return result

    if result.intent == "background":
        goal = result.payload["goal"]
        if chat_fn is None:
            result.response = "I can't run that in the background right now."
            result.handled_locally = True
            return result
        from core.task_queue import get_task_queue

        task_id = get_task_queue().submit(chat_fn, goal, label=goal[:60])
        result.response = f"Working on it in the background (task {task_id}). I'll let you know when it's done."
        result.handled_locally = True
        result.payload["task_id"] = task_id
        return result

    return result  # intent == "chat": caller proceeds exactly as before
