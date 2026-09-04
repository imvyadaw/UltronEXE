"""
Base specialist agent
======================
Common parent for every agent in specialist_agents/. Extends
agents/base_agent.py's BaseAgent (shared logger + describe() +
safe_call()) rather than reimplementing that, and adds the two things
the swarm needs on top that a plain agents/*.py agent doesn't:

  - `keywords`, a class-level list of terms this specialist should be
    matched against, and `can_handle(task)`, a cheap 0-1 keyword-overlap
    score task_delegation.py uses to pick who gets a given subtask -
    same zero-cost-routing-before-the-LLM philosophy as
    ai/multi_agent.py's _ROUTE_KEYWORDS, just scored instead of boolean.
  - `handle(task)`, the one entry point agent_orchestrator.py ever
    calls: it wraps a subclass's `_run(task)` in self.safe_call() so
    every specialist returns the same {"result": ...} / {"error": ...}
    shape no matter what it wraps underneath, and stamps the result
    with which agent produced it (consensus_engine.py needs that to
    attribute votes).

Subclasses implement `_run(self, task: Dict) -> Dict` and set
`capabilities` / `keywords` as class attributes - that's the whole
contract, same minimal-structure philosophy as BaseAgent itself.
"""

import re
from typing import Dict, List

from agents.base_agent import BaseAgent


class BaseSpecialistAgent(BaseAgent):
    """Common parent for specialist_agents/*.py. See module docstring."""

    #: Terms task_delegation.py scores a subtask's text against.
    #: Override per subclass - an empty list means this agent is never
    #: picked by keyword matching (still callable directly by name).
    keywords: List[str] = []

    def can_handle(self, task: Dict) -> float:
        """Cheap 0.0-1.0 relevance score for `task` against this agent's
        `keywords` - fraction of keywords present in the task's type +
        description text, capped at 1.0. No LLM call, offline."""
        if not self.keywords:
            return 0.0
        text = f"{task.get('type', '')} {task.get('description', '')}".lower()
        # Whole-word \b...\b search, not bare substring `in` - otherwise a
        # short keyword like "data" false-positives inside "database" or
        # "code" inside "encode", misrouting the task to the wrong agent.
        hits = sum(1 for kw in self.keywords if re.search(rf"\b{re.escape(kw)}\b", text))
        return min(1.0, hits / len(self.keywords) * 2)

    def handle(self, task: Dict) -> Dict:
        """The one entry point agent_orchestrator.py calls. Wraps
        `_run(task)` in safe_call() and tags the result with `agent`
        so downstream (swarm_memory.py, consensus_engine.py) always
        knows who produced it, even on error."""
        result = self.safe_call(self._run, task)
        result.setdefault("agent", self.name)
        return result

    def _run(self, task: Dict) -> Dict:
        """Override in every subclass. `task` is at minimum
        {"type": str, "description": str}; specific specialists read
        additional keys off it (e.g. code_agent.py reads "action")."""
        raise NotImplementedError
