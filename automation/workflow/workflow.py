"""Workflow runner
================
Chain multiple existing AI tools (the same ones in ai/tools_schema.py /
core/executor.py) into a single named, saved workflow - e.g. a
"morning routine" that opens Chrome, checks the weather, and reads
notes back, run with one command instead of three.
"""

import json
import time
from pathlib import Path
from typing import Dict, List

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "workflows"


class WorkflowRunner:
    """Save and run multi-step sequences of existing tool calls."""

    def __init__(self):
        WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

    def save_workflow(self, workflow_name: str, steps: List[Dict]) -> Dict:
        """Save a workflow. Each step: {"tool": "<tool_name>", "arguments": {...}}."""
        try:
            path = WORKFLOWS_DIR / f"{workflow_name}.json"
            with open(path, "w") as f:
                json.dump(steps, f, indent=2)
            return {"success": True, "workflow_name": workflow_name, "step_count": len(steps)}
        except Exception as e:
            return {"error": str(e)}

    def list_workflows(self) -> Dict:
        """List all saved workflows."""
        try:
            names = [p.stem for p in WORKFLOWS_DIR.glob("*.json")]
            return {"workflows": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)}

    def get_workflow(self, workflow_name: str) -> Dict:
        """View the steps of a saved workflow."""
        path = WORKFLOWS_DIR / f"{workflow_name}.json"
        if not path.exists():
            return {"error": f"No workflow named '{workflow_name}'"}
        with open(path) as f:
            steps = json.load(f)
        return {"workflow_name": workflow_name, "steps": steps}

    def run_workflow(self, workflow_name: str, stop_on_error: bool = True, delay_between_steps: float = 0.5) -> Dict:
        """Run a saved workflow step by step, in order."""
        path = WORKFLOWS_DIR / f"{workflow_name}.json"
        if not path.exists():
            return {"error": f"No workflow named '{workflow_name}'"}
        try:
            from ai.tool_runtime import execute_tool_call as execute_tool

            with open(path) as f:
                steps = json.load(f)

            results = []
            for i, step in enumerate(steps):
                tool_name = step.get("tool")
                arguments = step.get("arguments", {})
                raw_result = execute_tool(tool_name, arguments)
                parsed = json.loads(raw_result)
                results.append({"step": i + 1, "tool": tool_name, "result": parsed})

                if stop_on_error and "error" in parsed:
                    return {
                        "success": False,
                        "workflow_name": workflow_name,
                        "failed_at_step": i + 1,
                        "results": results,
                    }
                time.sleep(delay_between_steps)

            return {"success": True, "workflow_name": workflow_name, "results": results}
        except Exception as e:
            return {"error": str(e)}

    def delete_workflow(self, workflow_name: str) -> Dict:
        """Delete a saved workflow."""
        path = WORKFLOWS_DIR / f"{workflow_name}.json"
        if not path.exists():
            return {"error": f"No workflow named '{workflow_name}'"}
        path.unlink()
        return {"success": True, "deleted": workflow_name}
