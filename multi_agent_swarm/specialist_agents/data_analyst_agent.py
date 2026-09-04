"""
Swarm data analyst agent
==========================
Specialist wrapper around skills/data/processor.py's DataProcessor
(unchanged - extension-routed read/write/filter/sort/aggregate across
CSV/JSON/Excel). Like devops_agent.py, dispatches through
DataProcessor.execute(action, **kwargs) so new actions the underlying
skill gains later need no change here.
"""

from typing import Dict

from skills.data.processor import DataProcessor
from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent

_RESERVED_TASK_KEYS = ("type", "description", "action")


class SwarmDataAnalystAgent(BaseSpecialistAgent):
    """Read, filter, sort, and aggregate CSV/JSON/Excel data, from the swarm."""

    capabilities = ["data", "csv", "excel", "analysis", "aggregate"]
    keywords = [
        "csv",
        "excel",
        "spreadsheet",
        "data",
        "analyze",
        "analysis",
        "chart",
        "aggregate",
        "statistics",
        "rows",
        "column",
        "dataset",
    ]

    def __init__(self):
        super().__init__("data_analyst", "Reads, filters, sorts, and aggregates CSV/JSON/Excel data")
        self._backend = DataProcessor()

    def _run(self, task: Dict) -> Dict:
        action = task.get("action")
        path = task.get("path")
        if not action or not path:
            return {
                "error": "A data task needs both 'action' and 'path'",
                "available_actions": self._backend.list_actions(),
            }
        params = {k: v for k, v in task.items() if k not in _RESERVED_TASK_KEYS and k != "path"}
        return self._backend.execute(action, path=path, **params)
