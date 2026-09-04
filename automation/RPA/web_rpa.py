"""
Web RPA skill (Phase 5)
=========================
Browser-based robotic process automation: define a named script as an
ordered list of steps (navigate / fill / click / extract) and play it
back through Selenium via skills/web/form_filler.py's FormFiller.
Mirrors the storage shape of automation/RPA/editor.py (JSON files under
storage/cache/) but keeps web scripts in their own folder, since their
steps have a different shape - URLs + CSS/XPath selectors instead of
screen coordinates. Desktop-based RPA lives in the sibling
automation/RPA/desktop_rpa.py.

Step shapes:
    {"type": "navigate", "url": "...", "wait_selector": "..."}
    {"type": "fill", "url": "...", "fields": [{"selector": "#id", "value": "..."}], "submit_selector": "..."}
    {"type": "click", "url": "...", "selector": "...", "by": "css"}
    {"type": "extract", "url": "...", "wait_selector": "..."}
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from skills.base_skill import BaseSkill
from skills.web.form_filler import FormFiller

WEB_RPA_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "web_rpa"


class WebRPA:
    """Storage + execution for named browser-automation scripts."""

    def __init__(self, headless: bool = True):
        WEB_RPA_DIR.mkdir(parents=True, exist_ok=True)
        self._filler = FormFiller(headless=headless)

    def _path(self, script_name: str) -> Path:
        return WEB_RPA_DIR / f"{script_name}.json"

    def _load(self, script_name: str) -> Dict:
        path = self._path(script_name)
        if not path.exists():
            return {"error": f"No web RPA script named '{script_name}'"}
        with open(path) as f:
            return json.load(f)

    def _save(self, script_name: str, data: Dict) -> None:
        with open(self._path(script_name), "w") as f:
            json.dump(data, f, indent=2)

    def _with_id(self, step: Dict) -> Dict:
        step = dict(step)
        step.setdefault("id", uuid.uuid4().hex[:8])
        return step

    # -- script CRUD ------------------------------------------------------
    def create_script(self, script_name: str, steps: Optional[List[Dict]] = None) -> Dict:
        if self._path(script_name).exists():
            return {"success": False, "error": f"Script '{script_name}' already exists"}
        data = {"name": script_name, "steps": [self._with_id(s) for s in (steps or [])]}
        self._save(script_name, data)
        return {"success": True, "script_name": script_name, "step_count": len(data["steps"])}

    def add_step(self, script_name: str, step: Dict) -> Dict:
        data = self._load(script_name)
        if "error" in data:
            return {"success": False, **data}
        data["steps"].append(self._with_id(step))
        self._save(script_name, data)
        return {"success": True, "script_name": script_name, "step_count": len(data["steps"])}

    def list_scripts(self) -> Dict:
        scripts = [p.stem for p in WEB_RPA_DIR.glob("*.json")]
        return {"success": True, "scripts": scripts, "count": len(scripts)}

    def delete_script(self, script_name: str) -> Dict:
        path = self._path(script_name)
        if not path.exists():
            return {"success": False, "error": f"No web RPA script named '{script_name}'"}
        path.unlink()
        return {"success": True, "deleted": script_name}

    # -- execution ------------------------------------------------------
    def _run_step(self, step: Dict) -> Dict:
        step_type = step.get("type")
        if step_type == "navigate":
            return self._filler.extract_after_render(step["url"], wait_selector=step.get("wait_selector"))
        if step_type == "fill":
            return self._filler.fill_form(
                step["url"],
                step.get("fields", []),
                submit_selector=step.get("submit_selector"),
            )
        if step_type == "click":
            return self._filler.click_element(step["url"], step["selector"], by=step.get("by", "css"))
        if step_type == "extract":
            return self._filler.extract_after_render(step["url"], wait_selector=step.get("wait_selector"))
        return {"success": False, "error": f"Unknown step type '{step_type}' - use navigate/fill/click/extract"}

    def play(self, script_name: str, stop_on_error: bool = True) -> Dict:
        data = self._load(script_name)
        if "error" in data:
            return {"success": False, **data}
        results = []
        for step in data.get("steps", []):
            result = self._run_step(step)
            results.append({"step": step, "result": result})
            if stop_on_error and not result.get("success", True):
                return {
                    "success": False,
                    "script_name": script_name,
                    "results": results,
                    "error": f"Stopped at step {step.get('id')}: {result.get('error')}",
                }
        return {"success": True, "script_name": script_name, "results": results}

    def run_ad_hoc(self, steps: List[Dict], stop_on_error: bool = True) -> Dict:
        """Run a list of steps directly, without saving them as a named script."""
        results = []
        for step in steps:
            result = self._run_step(step)
            results.append({"step": step, "result": result})
            if stop_on_error and not result.get("success", True):
                return {"success": False, "results": results, "error": result.get("error")}
        return {"success": True, "results": results}

    def close(self) -> Dict:
        return self._filler.close()


class WebRPASkill(BaseSkill):
    """Define, edit, and play back browser-based RPA scripts (Selenium-backed)."""

    name = "web_rpa"
    description = "Define and play back browser automation scripts (navigate/fill/click/extract steps)."
    category = "automation"

    def __init__(self, headless: bool = True):
        self._rpa = WebRPA(headless=headless)
        super().__init__()

    def register_actions(self) -> None:
        r = self._rpa
        self._actions = {
            "create_script": r.create_script,
            "add_step": r.add_step,
            "list_scripts": r.list_scripts,
            "delete_script": r.delete_script,
            "play": r.play,
            "run_ad_hoc": r.run_ad_hoc,
            "close": r.close,
        }
