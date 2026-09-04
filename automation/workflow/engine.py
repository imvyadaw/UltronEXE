"""
Workflow engine skill (Phase 5 facade)
========================================
Wraps automation/workflow/workflow.py's WorkflowRunner (save/list/get/
run/delete named sequences of tool calls) behind the common BaseSkill
interface used by the skill registry (see skills/base_skill.py).
"""

from skills.base_skill import BaseSkill
from automation.workflow.workflow import WorkflowRunner


class WorkflowEngine(BaseSkill):
    """Save, list, run, and delete named multi-step tool-call workflows."""

    name = "workflow_engine"
    description = "Save, list, run, and delete named multi-step automation workflows."
    category = "automation"

    def __init__(self):
        self._runner = WorkflowRunner()
        super().__init__()

    def register_actions(self) -> None:
        r = self._runner
        self._actions = {
            "save": r.save_workflow,
            "list": r.list_workflows,
            "get": r.get_workflow,
            "run": r.run_workflow,
            "delete": r.delete_workflow,
        }
