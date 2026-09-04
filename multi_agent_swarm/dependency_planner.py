"""
Dependency-aware task planner
==============================
Fixes a real gap in task_delegation.py's decompose(): it splits a
compound request on "then"/";"/". " and hands back independent
subtasks with no dependency edges between them - and agent_orchestrator.py
dispatches subtasks with no unmet dependency in *parallel* by default.

Concretely, the orchestrator's own documented usage example -
    "Research the top 3 Python web frameworks, then write a short
     summary comparing them"
- splits into two subtasks on "then" and, being independent by that
  split, can run BOTH IN PARALLEL. specialist_agents/writer_agent.py's
  _run() reads task["description"] as the content to write about -
  which after the split is just "write a short summary comparing
  them", with no path for research_agent's findings to ever reach it.
  The writer agent has no way to know what "them" refers to.

DependencyAwarePlanner fixes this at the planning stage, not by
patching every specialist:

  1. Ask the LLM (via ai_router, same as every other Ultron reasoning
     call) to decompose the request into subtasks AND say which
     earlier subtasks (by index) each one depends on.
  2. agent_orchestrator.py's DAG dispatcher (see _dispatch_dag) then
     runs subtasks in topological batches - independent subtasks
     still run in parallel, but a subtask with unmet dependencies
     waits for them.
  3. Right before a dependent subtask is dispatched, its dependencies'
     actual results are appended into its "description" field (the one
     field every specialist_agents/*.py._run() already reads) - no
     specialist needs to change to receive context now.

Fails closed exactly like task_delegation.py's own decompose(): if the
LLM call errors, returns unparseable JSON, or the dependency graph has
a cycle, this falls back to the OLD behavior - TaskDelegator.decompose()'s
plain offline split, all subtasks independent - so a broken LLM call
degrades to "current behavior", never to a worse one.
"""

import json
from typing import Dict, List, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.dependency_planner")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.dependency_planner")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router as _default_router_factory
except Exception as exc:  # pragma: no cover
    _default_router_factory = None
    logger.warning(f"[dependency_planner] ai.ai_router unavailable: {exc}")

from multi_agent_swarm.task_delegation import get_task_delegator, _TYPE_KEYWORDS

PLAN_PROMPT = """Break the following request into 1-6 subtasks for a team of \
specialists: {types}.

For each subtask, decide which earlier subtasks (by index, 0-based) it needs \
the OUTPUT of before it can run - e.g. a "write a summary of the research" \
subtask depends on the "research X" subtask that comes before it. A subtask \
with no dependency should have an empty depends_on list. Most requests have \
few or no dependencies - only add one where a subtask genuinely needs another's \
result to do its job.

Respond with ONLY a JSON array, nothing else, in this exact shape:
[{{"description": "...", "type": "one of {types}", "depends_on": [0, 1]}}]

Request: {request}"""

MAX_SUBTASKS = 6


class DependencyAwarePlanner:
    """plan(request) -> List[Dict] subtasks, each with an integer "order"
    and a "depends_on" list of earlier orders. Falls back to
    TaskDelegator.decompose()'s plain offline split (all independent)
    on any LLM failure or malformed/cyclic output."""

    def __init__(self, router_factory: Optional[callable] = None):
        self._router_factory = router_factory or _default_router_factory
        self._fallback_delegator = get_task_delegator()

    def plan(self, request: str) -> List[Dict]:
        if not request or not request.strip():
            return []

        if self._router_factory is not None:
            try:
                planned = self._plan_with_llm(request)
                if planned is not None:
                    return planned
            except Exception as e:
                logger.info(f"[dependency_planner] LLM planning failed, falling back to offline split: {e}")

        return self._fallback(request)

    def _plan_with_llm(self, request: str) -> Optional[List[Dict]]:
        types = ", ".join(sorted(_TYPE_KEYWORDS.keys()))
        text = self._router_factory().complete(
            PLAN_PROMPT.format(types=types, request=request), temperature=0.2, max_tokens=500
        )
        text = (text or "").strip().strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

        parsed = json.loads(text)
        if not isinstance(parsed, list) or not parsed:
            return None

        parsed = parsed[:MAX_SUBTASKS]
        n = len(parsed)
        subtasks: List[Dict] = []
        for i, item in enumerate(parsed):
            if not isinstance(item, dict) or not str(item.get("description", "")).strip():
                return None  # malformed entry - don't half-trust this plan
            deps_raw = item.get("depends_on") or []
            deps = sorted({int(d) for d in deps_raw if isinstance(d, (int, float)) and 0 <= int(d) < i})
            subtasks.append(
                {
                    "description": str(item["description"]).strip(),
                    "type": item.get("type") if item.get("type") in _TYPE_KEYWORDS else None,
                    "order": i,
                    "depends_on": deps,
                }
            )

        if self._has_cycle(subtasks):
            logger.info("[dependency_planner] LLM plan had a dependency cycle, falling back to offline split")
            return None

        return subtasks

    def _has_cycle(self, subtasks: List[Dict]) -> bool:
        # depends_on is already restricted to strictly-earlier indices
        # (0 <= d < i) at construction time, so a cycle is structurally
        # impossible here - this check stays purely as a safety net in
        # case that invariant is ever loosened.
        visiting: set = set()
        by_order = {t["order"]: t for t in subtasks}

        def visit(order: int, stack: set) -> bool:
            if order in stack:
                return True
            if order in visiting:
                return False
            visiting.add(order)
            for dep in by_order.get(order, {}).get("depends_on", []):
                if visit(dep, stack | {order}):
                    return True
            return False

        return any(visit(t["order"], set()) for t in subtasks)

    def _fallback(self, request: str) -> List[Dict]:
        plain = self._fallback_delegator.decompose(request)
        for t in plain:
            t["depends_on"] = []
        return plain


_planner: Optional[DependencyAwarePlanner] = None


def get_dependency_planner() -> DependencyAwarePlanner:
    global _planner
    if _planner is None:
        _planner = DependencyAwarePlanner()
    return _planner
