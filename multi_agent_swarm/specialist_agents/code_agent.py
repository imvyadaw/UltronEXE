"""
Swarm code agent
================
Specialist wrapper around agents/coding_agent.py's CodingAgent (unchanged,
same Groq-backed write/explain/review/fix) - adds keyword-based
can_handle() scoring and the swarm's uniform task-in/dict-out shape so
agent_orchestrator.py and task_delegation.py can dispatch to it exactly
like every other specialist_agents/*.py file, without knowing it's a
thin wrapper underneath.
"""

from typing import Dict

from agents.coding_agent import CodingAgent
from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent

#: task["action"] -> CodingAgent method name.
_ACTIONS = {
    "write": "write_code",
    "explain": "explain_code",
    "review": "review_code",
    "fix": "fix_code",
}


class SwarmCodeAgent(BaseSpecialistAgent):
    """Write, explain, review, and fix code, dispatched from the swarm."""

    capabilities = ["code", "coding", "programming", "debugging", "review"]
    keywords = [
        "code",
        "function",
        "class",
        "script",
        "program",
        "bug",
        "debug",
        "refactor",
        "implement",
        "api",
        "compile",
        "syntax",
        "error trace",
    ]

    def __init__(self):
        super().__init__("code", "Writes, explains, reviews, and fixes code")
        self._backend = CodingAgent()

    def _run(self, task: Dict) -> Dict:
        description = task.get("description") or task.get("prompt")
        if not description:
            return {"error": "No description/prompt provided for a code task"}

        action = (task.get("action") or "write").lower()
        method_name = _ACTIONS.get(action)
        if method_name is None:
            return {"error": f"Unknown code action '{action}' - use one of {list(_ACTIONS)}"}
        method = getattr(self._backend, method_name)

        if method_name == "write_code":
            return method(description, language=task.get("language"))
        if method_name == "fix_code":
            return method(description, error_message=task.get("error_message"))
        return method(description)
