"""
Planning
========
Breaks a multi-step user request ("organize my Downloads folder and
save a summary note") into an ordered list of tool calls for
core/executor.py to run - using the same tool schema already exposed to
the assistant (ai/tools_schema.py), just asked for structured JSON
instead of a chat reply.

Goes through ai.ai_router (like every other AI request in Ultron) instead
of holding its own Groq connection, so planning also gets automatic
online/offline fallback instead of hard-failing without GROQ_API_KEY.
"""

import json
from typing import Dict

from ai.ai_router import get_router

PLANNING_PROMPT = """You turn a user's multi-step goal into an ordered JSON list of tool calls.
Use ONLY these tool names: {tool_names}
Respond with ONLY a JSON array, nothing else - no prose, no markdown code fences:
[{{"tool": "tool_name", "arguments": {{"arg1": "value"}}}}, ...]
If a step needs no arguments, use an empty object.
Goal: {goal}"""


class Planner:
    """Decompose a goal into an ordered list of {"tool", "arguments"} steps."""

    def make_plan(self, goal: str) -> Dict:
        """Ask the LLM to break `goal` into an ordered list of tool-call steps."""
        text = ""
        try:
            from ai.tools_schema import TOOLS

            tool_names = [t["function"]["name"] for t in TOOLS]

            prompt = PLANNING_PROMPT.format(tool_names=tool_names, goal=goal)
            text = get_router().complete(prompt, temperature=0.2, max_tokens=800)
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()

            steps = json.loads(text)
            if not isinstance(steps, list):
                return {"error": "Model did not return a JSON list of steps", "raw": text[:300]}

            valid_steps = [s for s in steps if isinstance(s, dict) and s.get("tool") in tool_names]
            return {"goal": goal, "steps": valid_steps, "step_count": len(valid_steps)}
        except json.JSONDecodeError:
            return {"error": f"Could not parse a plan from the model's output: {text[:300]}"}
        except Exception as e:
            return {"error": str(e)}
