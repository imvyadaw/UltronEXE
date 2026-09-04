"""
Task delegation
================
Turns one free-text request into subtasks and picks who does each one.
Two separate, composable steps:

    decompose(request)          -> List[Dict] subtasks, no agent chosen yet
    assign(subtasks, agents)    -> same list, each with an "agent" key

kept apart so agent_orchestrator.py can re-run assign() against a
different/narrower set of agents (e.g. everyone except one that just
errored) without re-decomposing the original request, and so
consensus_engine.py's review flows can call assign()-equivalent
scoring directly without going through decompose() at all.

Decomposition itself is a simple, offline heuristic - split on
sentence-ish separators ("then", ";", ". ") - not an LLM call, on
purpose: same zero-cost-before-the-LLM philosophy as
ai/multi_agent.py's keyword routing. A caller that wants smarter
decomposition can pre-split the request itself and hand decompose()
one subtask at a time (it happily returns a single subtask for a
request with no separators).
"""

import re
from typing import Dict, List, Optional

# Mirrors specialist_agents/*.py's own `keywords`, duplicated here
# (rather than importing every specialist just to read a class
# attribute) so decompose() can guess a "type" per subtask before any
# agent is even instantiated - agent_orchestrator.py's lazy-import
# philosophy for agents themselves, applied to routing too.
_TYPE_KEYWORDS = {
    "code": ["code", "function", "class", "script", "program", "bug", "debug", "refactor", "implement"],
    "research": ["research", "search", "find information", "look up", "investigate", "sources"],
    "writer": ["write", "draft", "blog", "article", "email", "summary", "summarize", "outline"],
    "devops": ["deploy", "process", "service", "restart", "launch", "window", "app"],
    "data_analyst": ["csv", "excel", "spreadsheet", "data", "analyze", "aggregate", "dataset"],
    "security": ["password", "secure", "vulnerable", "vulnerability", "permission", "secret", "audit", "encrypt"],
}

_SPLIT_PATTERN = re.compile(r"\s*(?:,?\s+then\s+|;\s*|\.\s+(?=[A-Z]))\s*")


class TaskDelegator:
    """Decomposes requests into subtasks and assigns them to agents."""

    def decompose(self, request: str) -> List[Dict]:
        """Split `request` into subtasks and guess a `type` for each via
        keyword overlap against _TYPE_KEYWORDS. A request with no
        separators comes back as a single subtask."""
        if not request or not request.strip():
            return []

        pieces = [p.strip() for p in _SPLIT_PATTERN.split(request.strip()) if p.strip()]
        if not pieces:
            pieces = [request.strip()]

        return [{"description": piece, "type": self._guess_type(piece), "order": i} for i, piece in enumerate(pieces)]

    def _guess_type(self, text: str) -> Optional[str]:
        text_l = text.lower()
        best_type, best_hits = None, 0
        for agent_type, keywords in _TYPE_KEYWORDS.items():
            # Whole-word \b...\b search, not bare substring `in` - see
            # specialist_agents/base_specialist.py's can_handle() for why
            # (avoids "data" matching inside "database", etc.)
            hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", text_l))
            if hits > best_hits:
                best_type, best_hits = agent_type, hits
        return best_type

    def assign(self, subtasks: List[Dict], agents: Dict[str, object]) -> List[Dict]:
        """Attach an "agent" key to each subtask. `agents` maps agent
        name -> an object with .can_handle(task) -> float (any
        BaseSpecialistAgent qualifies). Ties broken round-robin across
        the whole batch so one agent doesn't absorb every ambiguous
        subtask; a subtask no agent scores above 0 for gets
        "agent": None so the caller can decide what to do with it."""
        if not agents:
            return [{**t, "agent": None} for t in subtasks]

        sorted(agents.keys())
        assigned: List[Dict] = []
        rr_cursor = 0
        for task in subtasks:
            scores = {name: agent.can_handle(task) for name, agent in agents.items()}
            best_score = max(scores.values()) if scores else 0.0
            if best_score <= 0.0:
                assigned.append({**task, "agent": None})
                continue
            top = sorted(name for name, s in scores.items() if s == best_score)
            chosen = top[rr_cursor % len(top)]
            rr_cursor += 1
            assigned.append({**task, "agent": chosen})
        return assigned


_delegator: Optional[TaskDelegator] = None


def get_task_delegator() -> TaskDelegator:
    global _delegator
    if _delegator is None:
        _delegator = TaskDelegator()
    return _delegator
