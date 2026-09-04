"""
Base skill
==========
Phase 4: common interface for every skills/<category>/<file>.py facade
(controller.py, handler.py, manager.py, scraper.py, processor.py,
messaging.py, automation.py, tools.py). Before this, each skill module
was a bag of methods with its own dict-return convention and no shared
error handling, action discovery, or health-check story. BaseSkill gives
them all:

  - a uniform `execute(action, **kwargs) -> Dict` entry point (what the
    AI tool layer / skill registry actually calls)
  - automatic exception handling, so a bug or missing dependency inside
    a skill comes back as `{"success": False, "error": ...}` instead of
    an unhandled traceback
  - `list_actions()` / `describe()` for self-discovery (useful for
    building tool schemas or a help command)
  - an optional `health_check()` a skill can override to report whether
    its credentials/dependencies are actually configured

Subclasses do two things:
  1. set class attributes `name`, `description`, `category`
  2. implement `register_actions(self)` to populate `self._actions`
     with `{"action_name": bound_callable}` - usually thin pass-throughs
     to the existing lower-level modules (app_manager.py, gmail.py,
     scheduler.py, etc.) rather than reimplementing any logic.
"""

import logging
import time
from typing import Callable, Dict, List

logger = logging.getLogger("ultron.skills")


class SkillError(Exception):
    """Raised for skill-level failures that aren't already a result dict."""


class BaseSkill:
    """Common base class for every skill facade in skills/."""

    name: str = "base_skill"
    description: str = "Base class for all Ultron skills."
    category: str = "general"

    def __init__(self):
        self._actions: Dict[str, Callable] = {}
        self.register_actions()

    # -- subclasses must implement ---------------------------------------
    def register_actions(self) -> None:
        """Populate self._actions with {action_name: callable}. Called once,
        from __init__, after any backend clients have been constructed."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement register_actions()")

    # -- discovery ------------------------------------------------------
    def list_actions(self) -> List[str]:
        return sorted(self._actions.keys())

    def describe(self) -> Dict:
        """Metadata about this skill - handy for building AI tool schemas
        or a `list what you can do` response."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "actions": self.list_actions(),
        }

    # -- uniform dispatch -------------------------------------------------
    def execute(self, action: str, **kwargs) -> Dict:
        """Dispatch `action` to its registered handler. Always returns a
        `{"success": bool, ...}` dict - unknown actions, bad arguments, and
        exceptions raised inside the handler are all caught and normalized
        here so callers never need their own try/except around a skill."""
        handler = self._actions.get(action)
        if handler is None:
            return {
                "success": False,
                "error": (
                    f"Unknown action '{action}' for skill '{self.name}'. "
                    f"Available actions: {', '.join(self.list_actions())}"
                ),
                "_skill": self.name,
                "_action": action,
            }

        started = time.time()
        try:
            result = handler(**kwargs)
            if not isinstance(result, dict):
                result = {"success": True, "result": result}
            result.setdefault("success", True)
            result["_skill"] = self.name
            result["_action"] = action
            result["_elapsed_ms"] = round((time.time() - started) * 1000, 1)
            return result
        except TypeError as e:
            logger.error("Bad arguments calling %s.%s: %s", self.name, action, e)
            return {
                "success": False,
                "error": f"Bad arguments for '{action}': {e}",
                "_skill": self.name,
                "_action": action,
            }
        except Exception as e:
            logger.exception("Skill '%s' action '%s' failed", self.name, action)
            return {
                "success": False,
                "error": str(e),
                "_skill": self.name,
                "_action": action,
            }

    # -- optional override ------------------------------------------------
    def health_check(self) -> Dict:
        """Report whether this skill's dependencies/credentials are ready.
        Default assumes yes; skills that wrap optional integrations
        (email, calendar, messaging, ...) should override this to check
        their client(s)' `is_configured()`."""
        return {"success": True, "skill": self.name, "configured": True}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} actions={self.list_actions()}>"
