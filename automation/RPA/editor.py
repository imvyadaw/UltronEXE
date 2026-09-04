"""RPA editor
==========
CRUD access to the steps inside a saved RPA script - insert, update,
delete, and reorder individual steps without re-recording the whole
thing. Also supports building a script from scratch, step by step,
with no recording involved at all.
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List

RPA_DIR = Path(__file__).resolve().parents[2] / "storage" / "cache" / "rpa"


class RPAEditor:
    """Read/modify the step list of a saved RPA script."""

    def __init__(self):
        RPA_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, script_name: str) -> Path:
        return RPA_DIR / f"{script_name}.json"

    def load(self, script_name: str) -> Dict:
        path = self._path(script_name)
        if not path.exists():
            return {"error": f"No RPA script named '{script_name}'"}
        with open(path) as f:
            return json.load(f)

    def _save(self, script_name: str, data: Dict) -> None:
        with open(self._path(script_name), "w") as f:
            json.dump(data, f, indent=2)

    def create_script(self, script_name: str, steps: List[Dict] = None) -> Dict:
        """Create a brand-new script from a list of steps (no recording needed)."""
        path = self._path(script_name)
        if path.exists():
            return {"error": f"Script '{script_name}' already exists"}
        steps = steps or []
        for step in steps:
            step.setdefault("id", str(uuid.uuid4())[:8])
        data = {"name": script_name, "steps": steps}
        self._save(script_name, data)
        return {"success": True, "script_name": script_name, "step_count": len(steps)}

    def list_scripts(self) -> Dict:
        scripts = [p.stem for p in RPA_DIR.glob("*.json")]
        return {"scripts": scripts, "count": len(scripts)}

    def insert_step(self, script_name: str, index: int, step: Dict) -> Dict:
        """Insert a step at a given position (0-based). index >= len appends."""
        data = self.load(script_name)
        if "error" in data:
            return data
        step = dict(step)
        step.setdefault("id", str(uuid.uuid4())[:8])
        steps = data.get("steps", [])
        index = max(0, min(index, len(steps)))
        steps.insert(index, step)
        data["steps"] = steps
        self._save(script_name, data)
        return {"success": True, "script_name": script_name, "inserted_at": index, "step_count": len(steps)}

    def update_step(self, script_name: str, step_id: str, fields: Dict) -> Dict:
        """Update fields on the step matching step_id."""
        data = self.load(script_name)
        if "error" in data:
            return data
        steps = data.get("steps", [])
        for step in steps:
            if step.get("id") == step_id:
                step.update(fields)
                self._save(script_name, data)
                return {"success": True, "script_name": script_name, "updated_step": step}
        return {"error": f"No step with id '{step_id}' in '{script_name}'"}

    def delete_step(self, script_name: str, step_id: str) -> Dict:
        """Remove the step matching step_id."""
        data = self.load(script_name)
        if "error" in data:
            return data
        steps = data.get("steps", [])
        new_steps = [s for s in steps if s.get("id") != step_id]
        if len(new_steps) == len(steps):
            return {"error": f"No step with id '{step_id}' in '{script_name}'"}
        data["steps"] = new_steps
        self._save(script_name, data)
        return {"success": True, "script_name": script_name, "step_count": len(new_steps)}

    def reorder_steps(self, script_name: str, ordered_step_ids: List[str]) -> Dict:
        """Reorder steps to match the given list of step ids. Every existing
        id must appear exactly once."""
        data = self.load(script_name)
        if "error" in data:
            return data
        steps = data.get("steps", [])
        by_id = {s["id"]: s for s in steps}
        if set(ordered_step_ids) != set(by_id.keys()):
            return {"error": "ordered_step_ids must contain exactly the existing step ids, each once"}
        data["steps"] = [by_id[sid] for sid in ordered_step_ids]
        self._save(script_name, data)
        return {"success": True, "script_name": script_name, "step_count": len(data["steps"])}

    def delete_script(self, script_name: str) -> Dict:
        path = self._path(script_name)
        if not path.exists():
            return {"error": f"No RPA script named '{script_name}'"}
        path.unlink()
        return {"success": True, "deleted": script_name}

    def rename_step_type(self, script_name: str, step_id: str, new_type: str) -> Dict:
        """Convenience wrapper around update_step for changing just the type."""
        return self.update_step(script_name, step_id, {"type": new_type})
