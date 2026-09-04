"""RPA player
==========
Replays a step-based script saved by recorder.py (or hand-built by
editor.py). Unlike automation/macro/macro.py's player, understands
richer step types beyond click/key: wait, open_app (delegates to
skills.app_control), run_tool (delegates to core.executor, so a script
can drive any existing Ultron tool), and screenshot (just logs a
checkpoint - no image comparison, kept intentionally simple).
"""

import json
import time
from pathlib import Path
from typing import Dict, List

try:
    import pyautogui

    pyautogui.FAILSAFE = False
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

RPA_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "rpa"


class RPAPlayer:
    """Replay a saved RPA script step by step."""

    def _load(self, script_name: str) -> Dict:
        path = RPA_DIR / f"{script_name}.json"
        if not path.exists():
            return {"error": f"No RPA script named '{script_name}'"}
        with open(path) as f:
            return json.load(f)

    def _run_step(self, step: Dict) -> Dict:
        step_type = step.get("type")
        try:
            if step_type == "click":
                if not HAS_PYAUTOGUI:
                    return {"error": "pyautogui not installed"}
                button = step.get("button", "left")
                button = "left" if "left" in button else ("right" if "right" in button else "middle")
                pyautogui.click(step["x"], step["y"], button=button)
                return {"success": True}

            if step_type == "key":
                if not HAS_PYAUTOGUI:
                    return {"error": "pyautogui not installed"}
                key = step.get("key", "")
                if len(key) == 1:
                    pyautogui.typewrite(key)
                else:
                    try:
                        pyautogui.press(key.lower())
                    except Exception:
                        from core.error_trace import log_swallowed as _lsw

                        _lsw("automation.RPA.player._run_step")
                return {"success": True}

            if step_type == "type_text":
                if not HAS_PYAUTOGUI:
                    return {"error": "pyautogui not installed"}
                pyautogui.typewrite(step.get("text", ""), interval=step.get("interval", 0.02))
                return {"success": True}

            if step_type == "wait":
                time.sleep(step.get("seconds", 1.0))
                return {"success": True}

            if step_type == "open_app":
                from skills.app_control.app_manager import AppControlManager

                return AppControlManager().open_app(step.get("app_name", ""))

            if step_type == "run_tool":
                from ai.tool_runtime import execute_tool_call as execute_tool

                result = execute_tool(step.get("tool", ""), step.get("arguments", {}))
                return json.loads(result)

            if step_type == "screenshot":
                return {"success": True, "note": "checkpoint (no image comparison performed)"}

            return {"error": f"Unknown step type: {step_type}"}
        except Exception as e:
            return {"error": str(e)}

    def play(self, script_name: str, speed: float = 1.0, loop: int = 1) -> Dict:
        """Replay a saved script. speed > 1 plays faster (shorter waits between
        steps), loop repeats the whole script that many times."""
        script = self._load(script_name)
        if "error" in script:
            return script
        steps: List[Dict] = script.get("steps", [])

        all_results = []
        for iteration in range(max(1, loop)):
            last_t = 0.0
            results = []
            for step in steps:
                gap = (step.get("t", last_t) - last_t) / max(speed, 0.01)
                if gap > 0:
                    time.sleep(min(gap, 3.0))
                last_t = step.get("t", last_t)
                result = self._run_step(step)
                results.append({"step_id": step.get("id"), "type": step.get("type"), "result": result})
                if "error" in result:
                    return {
                        "success": False,
                        "script_name": script_name,
                        "iteration": iteration + 1,
                        "failed_step": step,
                        "results_so_far": all_results + [results],
                    }
            all_results.append(results)

        return {"success": True, "script_name": script_name, "iterations_run": loop, "steps_per_iteration": len(steps)}

    def dry_run(self, script_name: str) -> Dict:
        """Validate a script's steps without actually executing anything -
        checks step types are recognized and required fields are present."""
        script = self._load(script_name)
        if "error" in script:
            return script
        valid_types = {"click", "key", "type_text", "wait", "open_app", "run_tool", "screenshot"}
        issues = []
        for i, step in enumerate(script.get("steps", [])):
            step_type = step.get("type")
            if step_type not in valid_types:
                issues.append(f"Step {i}: unknown type '{step_type}'")
            elif step_type == "click" and ("x" not in step or "y" not in step):
                issues.append(f"Step {i}: click step missing x/y")
            elif step_type == "open_app" and not step.get("app_name"):
                issues.append(f"Step {i}: open_app step missing app_name")
            elif step_type == "run_tool" and not step.get("tool"):
                issues.append(f"Step {i}: run_tool step missing tool")
        return {
            "script_name": script_name,
            "step_count": len(script.get("steps", [])),
            "valid": not issues,
            "issues": issues,
        }

    def list_scripts(self) -> Dict:
        try:
            scripts = [p.stem for p in RPA_DIR.glob("*.json")]
            return {"scripts": scripts, "count": len(scripts)}
        except Exception as e:
            return {"error": str(e)}
