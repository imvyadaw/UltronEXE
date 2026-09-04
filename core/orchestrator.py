"""
Orchestrator (Phase 30 - Core)
=================================
Every piece this module wires together already existed before Phase
30, each doing its own job well but with no single caller driving
them in order for a whole goal:

    intelligence/goal_manager/goal_manager.py   - stores the goal + steps
    planning/priority_manager.py                - orders which step is next
    ai/tool_selector.py                         - turns a step's plain-text
                                                   description into a tool call
    execution/action_manager.py                 - runs it (approval-gated)
    verification_engine / hardening.result_states - classifies the outcome
    verification/failure_detector.py            - decides what a failure
                                                   means (retry/heal/rollback/
                                                   replan/abandon)
    intelligence/self_healing/self_healing_engine.py - "self_heal" rung
    verification/rollback.py                    - "rollback" rung
    planning/replanner.py                       - "replan" rung
    autonomy/stop_conditions.py                 - safety ceiling for the
                                                   whole run

run_goal() is the new single entry point: give it a goal in plain
English, it creates/decomposes it via goal_manager, then works
through the steps by priority until done, stopped, or out of budget -
escalating each failure exactly one rung further than the last
instead of either giving up immediately or retrying forever.

This does not replace cognitive_core/autonomous_executor.py or
core/autonomous_engine.py - both remain valid, narrower loops for
their own callers. This is the broader loop for callers (main.py,
autonomy/task_loop.py once that lands) that want the full
plan-execute-verify-heal-approve pipeline with one call.
"""

import threading
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from hardening.result_states import ResultState

from intelligence.goal_manager.goal_manager import get_goal_manager
from planning.priority_manager import get_priority_manager
from planning.replanner import get_replanner
from execution.action_manager import get_action_manager
from verification.failure_detector import get_failure_detector
from verification.rollback import new_rollback_engine
from autonomy.stop_conditions import new_stop_conditions

logger = get_logger("ultron.orchestrator")


def _resolve_step_to_tool_call(step_description: str, fallback_text: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Best-effort: turn a plain-text step ('check disk space') into a
    {"tool": ..., "arguments": ...} call. Tries ai/tool_selector.py's LLM
    path first (select_with_llm - more accurate, needs a live AI
    backend); if that's unavailable (no API key/network - see
    ai.ai_router) or returns nothing, falls back to select()'s offline
    keyword-overlap heuristic instead of giving up, so a goal isn't
    unresolvable end-to-end just because the LLM backend is down.

    BUG FIXED (found by actually running run_goal() offline, not just
    reading the code): when a goal's title doesn't match any of
    goal_decomposer.py's keyword templates, it falls back to
    generic-scaffolding steps like "Clarify what success looks like
    for check disk space" / "Take the first concrete action on check
    disk space". select()'s keyword-overlap match sees the real
    intent words in the step ("check", "disk", "space") diluted among
    "clarify", "success", "looks", "like", "for" - scaffolding words
    that appear in EVERY fallback-template step regardless of the
    actual goal, and drag the confidence score below select()'s
    threshold. Every fallback-template step for every goal was
    therefore silently unresolvable offline, not just this one - the
    offline agent loop could never complete a goal whose title didn't
    literally contain learn/build/fix/prepare/research.

    Fix: if resolving the (possibly scaffolding-diluted) step text
    fails, retry once against fallback_text - the goal's raw title,
    caller-supplied, with none of the template wording - before
    giving up. This does not change behavior for steps that already
    resolve on their own (learn/build/fix/... templates keep the
    step's own richer wording, which is more specific than the bare
    title, e.g. "Build the core of {title}" over just "{title}").

    Returns None only if every path finds nothing plausible - callers
    treat that step as non-actionable and skip it rather than crashing
    the whole run."""
    from ai.tool_selector import ToolSelector

    selector = ToolSelector()

    candidates = [step_description]
    if fallback_text and fallback_text != step_description:
        candidates.append(fallback_text)

    for text in candidates:
        try:
            picked = selector.select_with_llm(text)
            if picked and picked.get("tool"):
                return {"tool": picked["tool"], "arguments": picked.get("arguments", {})}
        except Exception as e:
            logger.debug(f"LLM tool resolution unavailable for '{text}': {e}")

    for text in candidates:
        try:
            picked = selector.select(text)
            if picked and picked.get("tool"):
                logger.debug(
                    f"Resolved '{step_description}' via offline keyword fallback on '{text}' (confidence={picked.get('confidence')})"
                )
                return {"tool": picked["tool"], "arguments": {}}
        except Exception as e:
            logger.debug(f"Offline tool resolution also failed for '{text}': {e}")

    return None


class Orchestrator:
    def __init__(self):
        self._goal_manager = get_goal_manager()
        self._priority = get_priority_manager()
        self._replanner = get_replanner()
        self._actions = get_action_manager()
        self._failures = get_failure_detector()

    def run_goal(
        self,
        title: str,
        description: str = "",
        urgency: float = 0.5,
        source: str = "user",
        max_iterations: int = 50,
        max_duration_seconds: float = 900.0,
    ) -> Dict:
        goal = self._goal_manager.create_goal(title, description, auto_decompose=True)
        if goal.get("error"):
            return {"success": False, "error": goal["error"]}

        goal_id = goal["id"]
        stop = new_stop_conditions(max_iterations=max_iterations, max_duration_seconds=max_duration_seconds)
        rollback = new_rollback_engine()
        attempt_counts: Dict[str, int] = {}
        step_log: List[Dict] = []
        own_step_ids = {step["id"] for step in goal.get("steps", [])}

        for step in goal.get("steps", []):
            self._priority.add(step["id"], {"description": step["description"], "goal_id": goal_id}, urgency=urgency)

        while True:
            check = stop.should_stop()
            if check.stopped:
                logger.info(f"Goal '{title}' stopping: {check.reason}")
                break

            # BUG FIXED (found by actually running two goals back to back in
            # the same process): planning/priority_manager.py is a SHARED
            # singleton queue by design, spanning every active goal at
            # once - but this loop called self._priority.next() and just
            # ran whatever came back, with no check that it belonged to
            # THIS goal_id. A step from a previous run_goal() call that
            # got "retry"-marked (and so was never .remove()'d) stayed in
            # the shared queue and could out-score this goal's own fresh
            # steps, so it got executed here under the wrong goal's
            # step_log/attempt_counts entirely - no crash, no error,
            # results just silently mixed between goals. Filter to this
            # goal's own step ids before taking the highest-priority one.
            item = next((it for it in self._priority.ordered() if it.item_id in own_step_ids), None)
            if item is None:
                break  # every step handled - success or abandoned

            step_id = item.item_id
            step_desc = item.payload["description"]
            attempt = attempt_counts.get(step_id, 0) + 1
            attempt_counts[step_id] = attempt

            outcome = self._run_step(step_desc, source, goal_title=title)
            state = ResultState.VERIFIED_SUCCESS if outcome.get("success") else ResultState.VERIFIED_FAILURE
            classification = self._failures.classify(state, attempt_number=attempt)
            step_log.append(
                {
                    "step_id": step_id,
                    "description": step_desc,
                    "attempt": attempt,
                    "outcome": outcome,
                    "classification": classification,
                }
            )

            stop.record_iteration(success=outcome.get("success", False))

            if classification["action"] == "none":
                self._goal_manager.advance_step(step_id)
                rollback.push(outcome.get("action", ""), {"result": outcome.get("result")}, label=step_desc)
                self._priority.remove(step_id)
                continue

            self._escalate(classification["action"], step_id, step_desc, outcome, rollback, goal_title=title)
            if classification["action"] == "abandon":
                self._priority.remove(step_id)
            else:
                self._priority.mark_retry(step_id)

        progress = self._goal_manager.get_progress(goal_id)
        return {
            # BUG FIXED: was progress.get("percent_complete", 0) - that key
            # never exists (progress_tracker.py returns "percent"), so this
            # silently defaulted to 0 and reported failure on every run,
            # even a goal that fully completed. Found by actually running
            # run_goal() to completion, not just reading the code.
            "success": progress.get("percent", 0) >= 100,
            "goal_id": goal_id,
            "progress": progress,
            "steps_run": len(step_log),
            "step_log": step_log,
            "stop_snapshot": stop.snapshot(),
        }

    def _run_step(self, step_description: str, source: str, goal_title: Optional[str] = None) -> Dict:
        call = _resolve_step_to_tool_call(step_description, fallback_text=goal_title)
        if call is None:
            return {
                "success": False,
                "action": step_description,
                "error": "could not resolve step to an executable tool call",
            }
        return self._actions.execute_action(call["tool"], call["arguments"], source=source)

    def _escalate(
        self, action: str, step_id: str, step_desc: str, outcome: Dict, rollback, goal_title: Optional[str] = None
    ) -> None:
        if action == "retry":
            logger.info(f"Retrying step '{step_desc}' unchanged")
            return

        if action == "self_heal":
            try:
                from intelligence.self_healing.self_healing_engine import get_self_healing_engine

                get_self_healing_engine().heal(
                    error=outcome.get("error", "step failed"),
                    executor=lambda strategy_name: self._run_step(step_desc, "self_healing", goal_title=goal_title).get(
                        "success", False
                    ),
                )
            except Exception as e:
                logger.warning(f"self_healing_engine unavailable, falling back to plain retry: {e}")
            return

        if action == "rollback":
            result = rollback.rollback_last()
            logger.info(f"Rollback for step '{step_desc}': {result}")
            return

        if action == "replan":
            new_steps = self._replanner.replan_step(step_desc, outcome.get("error", "unknown failure"))
            if new_steps:
                self._goal_manager.add_step(step_desc, new_steps[0])
            return

        if action == "abandon":
            logger.warning(f"Abandoning step '{step_desc}' after repeated failures")
            self._goal_manager.skip_step(step_id)


_instance: Optional[Orchestrator] = None
_instance_lock = threading.Lock()


def get_orchestrator() -> Orchestrator:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = Orchestrator()
    return _instance
