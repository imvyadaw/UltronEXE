"""
Intent resolver
================
Sits one step further than core/intent_router.py, exactly the way that
module itself sits one step further than ai/local_router.py (see its
own docstring). core.intent_router.classify() already owns WORKFLOW,
BACKGROUND, TASK_STATUS, and LIST_TASKS with confident regex patterns
and is never second-guessed here - this module only looks at text that
core.intent_router already gave up on (its CHAT fallback) and checks
whether it instead reads as an open-ended GOAL: something that wants
autonomous_executor's plan -> execute -> critique -> replan loop rather
than a single tool call or a fixed workflow.

Deliberately narrow, same philosophy as core.intent_router: only
matches an explicit "goal:"/"objective:" prefix or a small set of
"handle/figure out/sort out X end to end / autonomously / khud se"
phrasings. Anything else still falls through to CHAT exactly as
before - a wrong GOAL guess would kick off a multi-LLM-call pipeline
for what should have been a single quick reply, which is a much more
expensive mistake than intent_router's own wrong guesses.
"""

import re
from typing import Callable, Optional

from core.intent_router import IntentResult, classify as intent_router_classify, route as intent_router_route
from core.logger import get_logger

logger = get_logger("ultron.intent_resolver")

GOAL_PATTERNS = [
    re.compile(r"^\s*(?:goal|objective)\s*:\s*(?P<goal>.+)$", re.I),
    re.compile(
        r"^\s*(?:handle|figure out|sort out|manage|deal with)\s+(?P<goal>.+?)\s+"
        r"(?:end to end|fully|completely|autonomously|on your own)\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?P<goal>.+?)\s+(?:khud se|apne aap|end to end)\s+"
        r"(?:kar do|karo|handle karo|nipta do|sambhal lo)\s*$",
        re.I,
    ),
]


def _first_match(patterns, text: str):
    cleaned = text.strip()
    for pattern in patterns:
        m = pattern.match(cleaned)
        if m:
            return m
    return None


def classify(text: str) -> IntentResult:
    """core.intent_router's classification wins whenever it matches
    anything (workflow/background/task_status/list_tasks) - GOAL is
    only ever considered on its CHAT fallback, so nothing that already
    worked can be reclassified out from under it."""
    base = intent_router_classify(text)
    if base.matched:
        return base

    m = _first_match(GOAL_PATTERNS, text)
    if m:
        goal = m.group("goal").strip()
        if goal:
            return IntentResult(intent="goal", matched=True, payload={"goal": goal})

    return base  # intent == "chat"


def route(text: str, chat_fn: Optional[Callable[[str], str]] = None, run_async: bool = True) -> IntentResult:
    """Same contract as core.intent_router.route(): classify + execute
    for intents this layer owns, and transparently delegate to
    core.intent_router.route() for everything else - so a caller can
    swap intent_router.route -> intent_resolver.route without any other
    change, and get GOAL handling on top for free.
    """
    result = classify(text)
    if result.intent != "goal":
        # Not GOAL - hand off to core.intent_router.route() unchanged so
        # workflow/background/task_status/list_tasks/chat all behave
        # exactly as they did before this module existed.
        return intent_router_route(text, chat_fn)

    goal = result.payload["goal"]
    from cognitive_core.autonomous_executor import get_autonomous_executor

    executor = get_autonomous_executor()

    if run_async:
        from core.task_queue import get_task_queue

        task_id = get_task_queue().submit(executor.run_goal, goal, label=f"goal:{goal[:50]}")
        result.response = f"Working on '{goal}' autonomously (task {task_id}). I'll let you know when it's done."
        result.handled_locally = True
        result.payload["task_id"] = task_id
        return result

    outcome = executor.run_goal(goal)
    ok = outcome.get("satisfied", False)
    result.response = (
        f"Done - '{goal}' looks achieved."
        if ok
        else f"I made progress on '{goal}' but couldn't fully confirm it worked "
        f"({outcome.get('stopped_reason') or 'see result for details'})."
    )
    result.handled_locally = True
    result.payload["result"] = outcome
    return result
