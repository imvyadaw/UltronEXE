"""System macro engine
======================
Not to be confused with automation/macro/macro.py's MacroRecorder,
which records and replays real mouse-click/key-press *input events*
via pynput/pyautogui. This module has nothing to do with input
simulation - a "macro" here is a named, saved list of system_control
manager-method calls, e.g. a "night_mode" macro that calls
ThemeManager.set_dark_mode(True), SoundManager.set_default_playback_
device(...), and NotificationManager.set_focus_assist_mode(...) in one
shot instead of three separate requests.

Each step is {"module": "system_control.ui.theme_manager",
"class": "ThemeManager", "method": "set_dark_mode",
"kwargs": {"enabled": true}}. Steps are resolved and called directly
(no AI tool-name indirection) so this works for ANY system_control
manager without this module needing to know about it in advance.

Saving/listing/viewing is inert. Running a macro is confirm-gated as a
whole - individual steps are called with confirm=True baked in via
kwargs if the target method needs it, since the point of confirming
the macro is confirming everything it does together.
"""

import importlib
import json
from pathlib import Path
from typing import Dict, List

MACROS_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "system_macros"


class SystemMacroEngine:
    """Save, list, run, and delete named macros of system_control method calls."""

    def __init__(self):
        MACROS_DIR.mkdir(parents=True, exist_ok=True)

    def _path_for(self, name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in ("_", "-"))[:100]
        return MACROS_DIR / f"{safe}.json"

    def save_macro(self, name: str, steps: List[Dict]) -> Dict:
        """Save a macro. Each step:
        {"module": "system_control.ui.theme_manager", "class": "ThemeManager",
         "method": "set_dark_mode", "kwargs": {"enabled": true}}"""
        if not name or not steps:
            return {"error": "name and steps must both be non-empty"}
        for i, step in enumerate(steps):
            if not step.get("module") or not step.get("class") or not step.get("method"):
                return {"error": f"Step {i + 1}: module, class, and method are all required"}
            if not step["module"].startswith("system_control."):
                return {"error": f"Step {i + 1}: module must be under system_control. (got '{step['module']}')"}
        path = self._path_for(name)
        try:
            path.write_text(json.dumps(steps, indent=2), encoding="utf-8")
            return {"success": True, "name": path.stem, "step_count": len(steps)}
        except Exception as e:
            return {"error": str(e)}

    def list_macros(self) -> Dict:
        """List all saved macros."""
        try:
            names = sorted(p.stem for p in MACROS_DIR.glob("*.json"))
            return {"success": True, "macros": names, "count": len(names)}
        except Exception as e:
            return {"error": str(e)}

    def get_macro(self, name: str) -> Dict:
        """View a saved macro's steps."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No macro named '{name}'"}
        try:
            return {"success": True, "name": path.stem, "steps": json.loads(path.read_text(encoding="utf-8"))}
        except Exception as e:
            return {"error": str(e)}

    def delete_macro(self, name: str, confirm: bool = False) -> Dict:
        """Delete a saved macro. Confirm-gated."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No macro named '{name}'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete macro '{path.stem}'",
                "message": "Call again with confirm=true to apply.",
            }
        path.unlink()
        return {"success": True, "name": path.stem, "deleted": True}

    def run_macro(self, name: str, stop_on_error: bool = True, confirm: bool = False) -> Dict:
        """Run a saved macro, step by step, in order. Confirm-gated."""
        path = self._path_for(name)
        if not path.exists():
            return {"error": f"No macro named '{name}'"}
        try:
            steps = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"Could not read macro: {e}"}
        if not confirm:
            summary = ", ".join(f"{s['class']}.{s['method']}" for s in steps)
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would run macro '{name}' ({len(steps)} steps: {summary})",
                "message": "Call again with confirm=true to apply.",
            }
        results = []
        for i, step in enumerate(steps):
            try:
                mod = importlib.import_module(step["module"])
                cls = getattr(mod, step["class"])
                instance = cls()
                method = getattr(instance, step["method"])
                kwargs = dict(step.get("kwargs", {}))
                kwargs.setdefault("confirm", True)
                try:
                    result = method(**kwargs)
                except TypeError:
                    # method doesn't accept confirm= - retry without it
                    kwargs.pop("confirm", None)
                    result = method(**kwargs)
            except Exception as e:
                result = {"error": str(e)}
            results.append({"step": i + 1, "call": f"{step['class']}.{step['method']}", "result": result})
            if stop_on_error and isinstance(result, dict) and "error" in result:
                return {"success": False, "name": name, "failed_at_step": i + 1, "results": results}
        return {"success": True, "name": name, "results": results}
