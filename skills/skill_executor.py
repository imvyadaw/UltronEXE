"""
Skill Executor (Phase 30 - Skills)
=====================================
skills/base_skill.py's BaseSkill.execute() already gives every
individual skill instance a uniform dispatch (see its own docstring)
- but nothing resolves *which* BaseSkill instance to call by name, or
feeds the result back to intelligence/skill_builder/skill_store.py so
skill_builder's usage stats (record_usage / record_tool_outcome) stay
accurate for skills invoked this way. SkillExecutor is that one layer
up: run(skill_name, action, **kwargs) finds (and caches) the right
BaseSkill subclass instance, calls its .execute(), and records the
outcome.

Discovery: skills are looked up by class attribute `name` across the
BaseSkill subclasses already importable from the skills/ package tree
(skills/file, skills/ai, skills/utilities, ...). This intentionally
does not introduce a separate skills/registry.py - subclass discovery
via BaseSkill.__subclasses__() is enough for the current skill count,
and adding a heavier registry is easy later without changing this
module's public API.
"""

import importlib
import pkgutil
import threading
from typing import Dict, Optional

from core.logger import get_logger
from skills.base_skill import BaseSkill

logger = get_logger("ultron.skills.skill_executor")


class SkillExecutor:
    def __init__(self):
        self._instances: Dict[str, BaseSkill] = {}
        self._discovered = False
        self._lock = threading.Lock()

    def _discover(self):
        """Import every module under skills/ once, so every BaseSkill
        subclass has been defined and is visible via __subclasses__().
        Best-effort per-module - one broken skill module must not stop
        the rest from loading."""
        with self._lock:
            if self._discovered:
                return
            import skills

            for _, modname, _ in pkgutil.walk_packages(skills.__path__, prefix="skills."):
                try:
                    importlib.import_module(modname)
                except Exception as e:
                    logger.debug(f"Skipped skill module '{modname}': {e}")
            self._discovered = True

    def _resolve(self, skill_name: str) -> Optional[BaseSkill]:
        if skill_name in self._instances:
            return self._instances[skill_name]

        self._discover()
        for cls in BaseSkill.__subclasses__():
            if getattr(cls, "name", None) == skill_name:
                try:
                    instance = cls()
                except Exception as e:
                    logger.error(f"Failed to instantiate skill '{skill_name}': {e}")
                    return None
                self._instances[skill_name] = instance
                return instance
        return None

    def run(self, skill_name: str, action: str, **kwargs) -> Dict:
        skill = self._resolve(skill_name)
        if skill is None:
            return {"success": False, "error": f"Unknown skill '{skill_name}'"}

        result = skill.execute(action, **kwargs)

        try:
            from intelligence.skill_builder.skill_store import get_skill_store

            get_skill_store().record_tool_outcome(f"{skill_name}.{action}", bool(result.get("success")))
        except Exception as e:
            logger.debug(f"Could not record skill outcome: {e}")

        return result

    def list_available(self) -> Dict:
        self._discover()
        return {cls.name: cls.description for cls in BaseSkill.__subclasses__() if getattr(cls, "name", None)}


_instance: Optional[SkillExecutor] = None


def get_skill_executor() -> SkillExecutor:
    global _instance
    if _instance is None:
        _instance = SkillExecutor()
    return _instance
