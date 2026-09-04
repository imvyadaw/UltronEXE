"""
Workflow Engine
===============
Richer sibling of automation/workflow/workflow.py (WorkflowRunner), which
only plays back a flat list of tool calls in order. This engine adds the
three things a "real" multi-step task usually needs:

  1. Variable passing between steps - a later step can reference an
     earlier step's result with "{{step1.output.some_field}}" anywhere
     in its arguments (dot-path into that step's parsed JSON result).
  2. Conditional steps - a step can carry "run_if": {"step": 1, "path":
     "output.success", "equals": true} and is skipped if that doesn't
     hold, instead of failing the whole workflow.
  3. Per-step retry - via core.error_handler, so a flaky step (e.g. a
     network call) doesn't take the whole workflow down.

Workflows are stored as JSON under storage/cache/workflows_advanced/,
separate from the simple WorkflowRunner's storage so both can coexist -
existing simple workflows keep working unchanged. Each step:

    {
        "tool": "open_url",
        "arguments": {"url": "https://example.com"},
        "run_if": {"step": 1, "path": "output.success", "equals": true},  # optional
        "max_retries": 1,                                                 # optional
        "label": "open homepage"                                         # optional
    }

Run synchronously with run_workflow(), or hand off to core.task_queue
with run_workflow_async() so it doesn't block the caller.
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.error_handler import get_error_handler
from core.logger import get_logger

logger = get_logger("ultron.workflow_engine")

_engine: Optional["WorkflowEngine"] = None

VAR_PATTERN = re.compile(r"\{\{\s*step(\d+)\.([a-zA-Z0-9_.]+)\s*\}\}")


def _dig(obj: Any, dotted_path: str) -> Any:
    """obj['a']['b'][0] style lookup via a dotted path like 'a.b.0'."""
    cur = obj
    for part in dotted_path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _interpolate(value: Any, step_results: Dict[int, Dict]) -> Any:
    """Recursively substitute {{stepN.path}} references inside strings,
    dicts, and lists. A value that is *only* a single reference keeps
    its native type (e.g. a bool/number/dict), not stringified."""
    if isinstance(value, str):
        match = VAR_PATTERN.fullmatch(value.strip())
        if match:
            step_num, path = int(match.group(1)), match.group(2)
            return _dig(step_results.get(step_num, {}), path)

        def _sub(m):
            step_num, path = int(m.group(1)), m.group(2)
            resolved = _dig(step_results.get(step_num, {}), path)
            return "" if resolved is None else str(resolved)

        return VAR_PATTERN.sub(_sub, value)

    if isinstance(value, dict):
        return {k: _interpolate(v, step_results) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, step_results) for v in value]
    return value


class WorkflowEngine:
    """Save, inspect, and run multi-step workflows with variables, branching
    and retries."""

    def __init__(self):
        from config import STORAGE_DIR

        self._dir = STORAGE_DIR / "cache" / "workflows_advanced"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._error_handler = get_error_handler()

    # -- storage -------------------------------------------------------
    def _path_for(self, name: str) -> Path:
        return self._dir / f"{name}.json"

    def save_workflow(self, name: str, steps: List[Dict]) -> Dict:
        try:
            with open(self._path_for(name), "w", encoding="utf-8") as f:
                json.dump(steps, f, indent=2)
            return {"success": True, "workflow_name": name, "step_count": len(steps)}
        except Exception as e:
            return {"error": str(e)}

    def get_workflow(self, name: str) -> Dict:
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No advanced workflow named '{name}'"}
        with open(path, encoding="utf-8") as f:
            return {"workflow_name": name, "steps": json.load(f)}

    def list_workflows(self) -> Dict:
        names = sorted(p.stem for p in self._dir.glob("*.json"))
        return {"count": len(names), "workflows": names}

    def delete_workflow(self, name: str) -> Dict:
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No advanced workflow named '{name}'"}
        path.unlink()
        return {"success": True, "deleted": name}

    # -- execution -------------------------------------------------------
    def _run_steps(self, steps: List[Dict], stop_on_error: bool, delay: float) -> Dict:
        step_results: Dict[int, Dict] = {}
        report: List[Dict] = []

        for i, step in enumerate(steps, start=1):
            tool_name = step.get("tool")
            label = step.get("label", tool_name)
            run_if = step.get("run_if")

            if run_if:
                ref = step_results.get(run_if.get("step"), {})
                actual = _dig(ref, run_if.get("path", ""))
                if actual != run_if.get("equals"):
                    report.append(
                        {
                            "step": i,
                            "tool": tool_name,
                            "label": label,
                            "skipped": True,
                            "reason": f"run_if not met ({actual!r} != {run_if.get('equals')!r})",
                        }
                    )
                    step_results[i] = {"skipped": True}
                    continue

            raw_args = step.get("arguments", {})
            resolved_args = _interpolate(raw_args, step_results)

            # Deep-audit fix: was calling core.executor.execute_tool directly,
            # which skips ai.tool_runtime.execute_tool_from_dict's
            # ActionPipeline routing - so every workflow-driven call (used by
            # cognitive_core.autonomous_executor and core.orchestrator, i.e.
            # every "autonomous"/multi-step goal) bypassed
            # PermissionGate.DESTRUCTIVE_TOOLS confirmation entirely. Lazy
            # import matches core/executor.py's own _workflow_engine() lazy
            # pattern and avoids a load-order dependency between the two
            # modules.
            from ai.tool_runtime import execute_tool_from_dict

            tool_dict = {"tool": tool_name, **resolved_args}
            outcome = self._error_handler.run_safely(
                execute_tool_from_dict,
                tool_dict,
                max_retries=step.get("max_retries", 0),
                context=label,
            )

            output = outcome.get("result") if outcome.get("success") else {"error": outcome.get("error")}
            step_results[i] = {"output": output, "success": outcome.get("success", False)}
            report.append(
                {
                    "step": i,
                    "tool": tool_name,
                    "label": label,
                    "arguments": resolved_args,
                    "success": outcome.get("success", False),
                    "result": output,
                }
            )

            if not outcome.get("success") and stop_on_error:
                return {"success": False, "failed_at_step": i, "steps": report}

            if delay:
                time.sleep(delay)

        return {"success": True, "steps": report}

    def run_workflow(self, name: str, stop_on_error: bool = True, delay_between_steps: float = 0.3) -> Dict:
        wf = self.get_workflow(name)
        if "error" in wf:
            return wf
        result = self._run_steps(wf["steps"], stop_on_error, delay_between_steps)
        result["workflow_name"] = name
        return result

    def run_ad_hoc(self, steps: List[Dict], stop_on_error: bool = True, delay_between_steps: float = 0.3) -> Dict:
        """Run a list of steps without saving it as a named workflow first -
        useful for a one-off multi-step plan the LLM assembles on the fly."""
        return self._run_steps(steps, stop_on_error, delay_between_steps)

    def run_workflow_async(self, name: str, stop_on_error: bool = True) -> Dict:
        """Hand the whole workflow off to core.task_queue so the caller
        (main.py's input loop) doesn't block while it runs."""
        from core.task_queue import get_task_queue

        tq = get_task_queue()
        task_id = tq.submit(self.run_workflow, name, stop_on_error, label=f"workflow:{name}")
        return {"success": True, "task_id": task_id, "workflow_name": name}


def get_workflow_engine() -> WorkflowEngine:
    global _engine
    if _engine is None:
        _engine = WorkflowEngine()
    return _engine
