"""System automation pipeline
=============================
Not to be confused with automation/workflow/engine.py's WorkflowEngine
(WorkflowRunner), which chains named *AI tool calls* and therefore
requires `ai.tool_runtime` - i.e. the whole ULTRON AI stack - to be
importable when it runs. This module chains native OS-level jobs
directly (a saved PowerShell script, a saved batch script, a native
file backup, or a plain sleep) using only the plain manager classes in
this same package, with zero dependency on `ai/` or `core/`. That
matters because backup_scheduler.py hands pipelines like this to
Windows Task Scheduler to run unattended (e.g. at 2 AM, or at logon) -
those runs must work even when ULTRON's assistant process isn't
running at all, which a WorkflowRunner-based pipeline could not do.

Each step is `{"type": "powershell"|"batch"|"backup"|"wait", ...}`.
Saved pipelines live under storage/cache/system_pipelines/<name>.json,
same convention as WORKFLOWS_DIR/MACROS_DIR elsewhere.

Saving/listing/viewing is inert. Running a pipeline is confirm-gated
at this layer too (on top of whatever confirm-gating the individual
steps already do) since a pipeline is a bundle of several
consequential actions run back to back.
"""

import json
import time
from pathlib import Path
from typing import Dict, List

PIPELINES_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "system_pipelines"

VALID_STEP_TYPES = ("powershell", "batch", "backup", "wait")


class SystemAutomationPipeline:
    """Save, list, run, and delete named pipelines of native system jobs."""

    def __init__(self):
        PIPELINES_DIR.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in ("_", "-"))[:100]
        return PIPELINES_DIR / f"{safe}.json"

    def save_pipeline(self, name: str, steps: List[Dict]) -> Dict:
        """Save a pipeline. Each step is one of:
        {"type": "powershell", "script_name": "...", "timeout": 60}
        {"type": "batch", "script_name": "...", "arguments": "", "timeout": 60}
        {"type": "backup", "path": "..."}
        {"type": "wait", "seconds": 5}
        """
        if not name or not steps:
            return {"error": "name and steps must both be non-empty"}
        for i, step in enumerate(steps):
            if step.get("type") not in VALID_STEP_TYPES:
                return {"error": f"Step {i + 1}: type must be one of {VALID_STEP_TYPES}"}
        path = self._path_for(name)
        try:
            path.write_text(json.dumps(steps, indent=2), encoding="utf-8")
            return {"success": True, "name": path.stem, "step_count": len(steps)}
        except Exception as e:
            return {"error": str(e)}

    def list_pipelines(self) -> Dict:
        """List all saved pipelines."""
        try:
            names = sorted(p.stem for p in PIPELINES_DIR.glob("*.json"))
            return {"success": True, "pipelines": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)}

    def get_pipeline(self, name: str) -> Dict:
        """View a saved pipeline's steps."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No pipeline named '{name}'"}
        try:
            return {"success": True, "name": path.stem, "steps": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_pipeline(self, name: str, confirm: bool = False) -> Dict:
        """Delete a saved pipeline. Confirm-gated."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No pipeline named '{name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete pipeline '{path.stem}'",
                "message": "Call again with confirm=true to apply.",
            }
        path.unlink()
        return {"success": True, "name": path.stem, "deleted": True}

    def _run_step(self, step: Dict) -> Dict:
        step_type = step.get("type")
        if step_type == "powershell":
            from system_control.automation.powershell_manager import PowerShellScriptManager

            return PowerShellScriptManager().run_script(
                step["script_name"], timeout=step.get("timeout", 60), confirm=True
            )
        if step_type == "batch":
            from system_control.automation.batch_manager import BatchScriptManager

            return BatchScriptManager().run_script(
                step["script_name"], arguments=step.get("arguments", ""), timeout=step.get("timeout", 60), confirm=True
            )
        if step_type == "backup":
            from system_control.files.backup import FileBackup

            return FileBackup().backup_path(step["path"], confirm=True)
        if step_type == "wait":
            time.sleep(step.get("seconds", 1))
            return {"success": True, "waited_seconds": step.get("seconds", 1)}
        return {"error": f"Unknown step type: {step_type}"}

    def run_pipeline(self, name: str, stop_on_error: bool = True, confirm: bool = False) -> Dict:
        """Run a saved pipeline, step by step, in order. Confirm-gated -
        this is a bundle of native, already-individually-consequential
        actions (each step still runs with its own confirm=True, since
        confirming the pipeline as a whole is the point)."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No pipeline named '{name}'"}
        try:
            steps = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"Could not read pipeline: {e}"}
        if not confirm:
            summary = ", ".join(f"{s.get('type')}" for s in steps)
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run pipeline '{name}' ({len(steps)} steps: {summary})",
                "message": "Call again with confirm=true to apply.",
            }
        results = []
        for i, step in enumerate(steps):
            try:
                result = self._run_step(step)
            except Exception as e:
                result = {"error": str(e)}
            results.append({"step": i + 1, "type": step.get("type"), "result": result})
            if stop_on_error and isinstance(result, dict) and "error" in result:
                return {"success": False, "name": name, "failed_at_step": i + 1, "results": results}
        return {"success": True, "name": name, "results": results}


def run_pipeline_by_name(name: str) -> Dict:
    """CLI-friendly entry point with no confirm prompt needed - meant to
    be the target of a Windows Scheduled Task action (e.g.
    `python -m system_control.automation.workflow_engine <name>`),
    where there's no interactive caller to confirm anything."""
    return SystemAutomationPipeline().run_pipeline(name, confirm=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print(json.dumps(run_pipeline_by_name(sys.argv[1]), indent=2))
    else:
        print("Usage: python -m system_control.automation.workflow_engine <pipeline_name>")
