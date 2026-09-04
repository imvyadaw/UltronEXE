"""
Goal planner
============
core/planner.py + ai/planning.py already turn a goal straight into a
flat list of tool calls in one LLM round-trip - fine for something
small ("open Chrome and search for X"), but a genuinely open-ended goal
("clean up my Downloads folder and email myself a summary") plans
better as a short list of human-readable *sub-goals* first, each of
which task_decomposer.py then turns into tool-call steps on its own.
Two smaller LLM calls with a clear intermediate artifact beat one giant
call trying to do both jumps at once, and each sub-goal can be
individually re-planned via `feedback` if self_critique_agent decides
it wasn't achieved - see autonomous_executor.py for that loop.

ai.planning.Planner itself is reused unchanged for the "quick" path
(quick_plan) - this module never re-implements tool-schema validation,
it only adds the sub-goal layer on top.
"""

import json
from typing import Dict, List, Optional

from ai.ai_router import get_router
from ai.planning import Planner as ToolPlanGenerator

SUBGOAL_PROMPT = """You break a user's goal into a short ordered list of sub-goals - \
milestones, not tool calls. Each sub-goal should be small enough to plan on its own \
but big enough to be a meaningful checkpoint (roughly 1-5 sub-goals for most requests).

Respond with ONLY a JSON array, nothing else - no prose, no markdown fences:
[{{"title": "short imperative sub-goal", "success_criteria": "how to tell it worked"}}, ...]

Goal: {goal}{feedback_block}"""

FEEDBACK_BLOCK_TEMPLATE = """

A previous attempt at this goal was not fully successful. Take this into account \
when re-planning - avoid repeating the same approach:
{feedback}"""

MAX_SUBGOALS = 6


class GoalPlanner:
    """Breaks a goal into sub-goals (this module) or straight into tool
    steps for simple goals (delegates to ai.planning.Planner)."""

    def __init__(self):
        self._tool_planner = ToolPlanGenerator()

    def plan_goal(self, goal: str, feedback: Optional[str] = None) -> Dict:
        """LLM call -> ordered list of {"title", "success_criteria"}
        sub-goals. `feedback` (usually self_critique_agent's `reason` /
        `suggested_fix` from a prior attempt) gets folded into the
        prompt so a replan isn't a blind repeat. Always returns a dict
        with either "subgoals" or "error" - never raises.
        """
        text = ""
        try:
            feedback_block = FEEDBACK_BLOCK_TEMPLATE.format(feedback=feedback) if feedback else ""
            prompt = SUBGOAL_PROMPT.format(goal=goal, feedback_block=feedback_block)
            text = get_router().complete(prompt, temperature=0.3, max_tokens=500)
            text = text.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()

            subgoals = json.loads(text)
            if not isinstance(subgoals, list) or not subgoals:
                return self._single_subgoal_fallback(goal)

            cleaned: List[Dict] = []
            for sg in subgoals[:MAX_SUBGOALS]:
                if isinstance(sg, dict) and sg.get("title"):
                    cleaned.append(
                        {
                            "title": str(sg["title"]).strip(),
                            "success_criteria": str(sg.get("success_criteria", "")).strip(),
                        }
                    )
            if not cleaned:
                return self._single_subgoal_fallback(goal)

            return {"goal": goal, "subgoals": cleaned, "subgoal_count": len(cleaned)}
        except json.JSONDecodeError:
            # Model didn't return valid JSON - degrade gracefully to a
            # single sub-goal (the whole goal, unchanged) rather than
            # failing the entire pipeline over a formatting slip.
            return self._single_subgoal_fallback(goal)
        except Exception as e:
            return {"error": str(e)}

    def _single_subgoal_fallback(self, goal: str) -> Dict:
        return {
            "goal": goal,
            "subgoals": [{"title": goal, "success_criteria": ""}],
            "subgoal_count": 1,
            "fallback": True,
        }

    def quick_plan(self, goal: str) -> Dict:
        """Skips the sub-goal layer entirely - same as core/planner.py's
        Planner.plan(), for a goal simple enough to go straight to a
        flat tool-call list."""
        return self._tool_planner.make_plan(goal)


_planner: Optional[GoalPlanner] = None


def get_goal_planner() -> GoalPlanner:
    global _planner
    if _planner is None:
        _planner = GoalPlanner()
    return _planner
