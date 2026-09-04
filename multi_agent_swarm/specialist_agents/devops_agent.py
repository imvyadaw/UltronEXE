"""
Swarm devops agent
====================
Specialist wrapper around skills/windows/manager.py's WindowsManager
(unchanged - open/close apps, window geometry/snap/minimize/tile,
process listing). "Devops" for a desktop assistant means the local
machine's processes and windows rather than cloud infrastructure - the
closest existing capability Ultron has to service/process management,
so this wraps it rather than duplicating it.

Goes through WindowsManager.execute(action, **kwargs) - BaseSkill's
uniform entry point - rather than each individual method, so any
action skills/windows/manager.py adds later is automatically available
here with no changes to this file.
"""

from typing import Dict

from skills.windows.manager import WindowsManager
from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent

_RESERVED_TASK_KEYS = ("type", "description", "action")


class SwarmDevOpsAgent(BaseSpecialistAgent):
    """Open/close apps and manage windows/processes, dispatched from the swarm."""

    capabilities = ["devops", "process", "window", "app", "system"]
    keywords = [
        "deploy",
        "process",
        "service",
        "restart",
        "launch",
        "open app",
        "close app",
        "window",
        "monitor",
        "running",
        "pipeline",
        "infra",
    ]

    def __init__(self):
        super().__init__("devops", "Opens/closes apps and manages windows and processes")
        self._backend = WindowsManager()

    def _run(self, task: Dict) -> Dict:
        action = task.get("action")
        if not action:
            return {
                "error": "No action provided for a devops task",
                "available_actions": self._backend.list_actions(),
            }
        params = {k: v for k, v in task.items() if k not in _RESERVED_TASK_KEYS}
        return self._backend.execute(action, **params)
