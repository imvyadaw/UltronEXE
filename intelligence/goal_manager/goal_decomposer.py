"""
Goal Decomposer (Phase 19.3 - Goal Manager)
===============================================
Breaks a goal's title/description down into an ordered list of
concrete steps, then hands them to goal_store.py. Fully offline and
rule-based - no LLM call, no network: a small keyword -> template
table covers common goal shapes (learning something, shipping/
building something, fixing/debugging something, preparing for an
event, research), and anything that matches nothing falls back to a
generic three-step plan. Callers can always add/edit/reorder steps
by hand afterwards through goal_store directly - decompose() is a
starting point, not a locked plan.
"""

import re
import threading
from typing import Dict, List, Optional

from intelligence.goal_manager.goal_store import get_goal_store

_instance: Optional["GoalDecomposer"] = None
_instance_lock = threading.Lock()

# keyword -> ordered step templates. "{title}" is substituted with the
# goal's title. Checked in order; first match wins.
_TEMPLATES = [
    (
        r"\blearn|study|master\b",
        [
            "Identify what 'done' looks like for {title}",
            "Gather learning resources for {title}",
            "Work through the basics of {title}",
            "Practice / apply {title} on a small example",
            "Review gaps and revisit weak spots in {title}",
        ],
    ),
    (
        r"\bbuild|ship|create|develop|implement\b",
        [
            "Write down requirements for {title}",
            "Sketch the design/approach for {title}",
            "Build the core of {title}",
            "Test {title}",
            "Polish and finalize {title}",
        ],
    ),
    (
        r"\bfix|debug|resolve|troubleshoot\b",
        [
            "Reproduce the issue behind {title}",
            "Narrow down the root cause of {title}",
            "Apply a fix for {title}",
            "Verify {title} is actually resolved",
        ],
    ),
    (
        r"\bprepare|prep|plan\b.*\b(meeting|interview|exam|presentation|event)\b",
        [
            "List what needs to be ready for {title}",
            "Gather/create the materials for {title}",
            "Run through a dry pass of {title}",
            "Final check before {title}",
        ],
    ),
    (
        r"\bresearch|investigate|explore\b",
        [
            "Define the question behind {title}",
            "Collect sources/information on {title}",
            "Summarize findings on {title}",
            "Decide next action based on {title}",
        ],
    ),
]

_FALLBACK_TEMPLATE = [
    "Clarify what success looks like for {title}",
    "Take the first concrete action on {title}",
    "Follow through and close out {title}",
]


class GoalDecomposer:
    """Rule-based title/description -> ordered steps, plus a convenience
    method that decomposes and writes the steps straight into
    goal_store for a given goal_id."""

    def __init__(self):
        self._store = get_goal_store()

    def decompose(self, title: str, description: str = "") -> List[str]:
        """Return an ordered list of step descriptions for a goal. Does
        not touch storage - pure text in, list of strings out."""
        text = f"{title} {description}".lower()
        for pattern, template in _TEMPLATES:
            if re.search(pattern, text):
                return [step.format(title=title) for step in template]
        return [step.format(title=title) for step in _FALLBACK_TEMPLATE]

    def decompose_and_create(self, goal_id: str) -> Dict:
        """Look up the goal by id, decompose it, and write the resulting
        steps into goal_store as pending steps in order. Skips goals
        that already have steps, so it's safe to call more than once."""
        goal = self._store.get_goal(goal_id)
        if goal.get("error"):
            return goal
        if self._store.list_steps(goal_id):
            return {"error": f"goal {goal_id} already has steps"}

        steps = self.decompose(goal["title"], goal.get("description", ""))
        created = [self._store.add_step(goal_id, desc, order_index=i) for i, desc in enumerate(steps)]
        return {"goal_id": goal_id, "steps": created}


def get_goal_decomposer() -> GoalDecomposer:
    """Process-wide GoalDecomposer singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GoalDecomposer()
    return _instance
