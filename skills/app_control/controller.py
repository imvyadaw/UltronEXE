"""
App control skill (Phase 4 facade)
===================================
Exposes AppControlManager (skills/app_control/app_manager.py, itself a
composition of app_finder.py + app_detector.py + app_launcher.py + window
state) through the common BaseSkill interface, so the skill registry / AI
tool layer can call `execute("open", app_name="chrome")` instead of
importing the manager directly. No app-control logic lives here - it's
all still in app_manager.py and friends.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.app_control.app_manager import AppControlManager


class AppController(BaseSkill):
    """Unified open/close/find/manage-window-state facade for desktop apps."""

    name = "app_control"
    description = "Open, close, restart, find, and manage the window state of desktop applications."
    category = "system"

    def __init__(self):
        self._manager = AppControlManager()
        super().__init__()

    def register_actions(self) -> None:
        m = self._manager
        self._actions = {
            "open": m.open_app,
            "close": m.close_app,
            "restart": m.restart_app,
            "list_open": m.list_open_apps,
            "find": m.find_app,
            "status": m.app_status,
            "minimize": m.minimize_app,
            "maximize": m.maximize_app,
            "focus": m.focus_app,
            "close_category": m.close_all_by_category,
            "kill_unresponsive": m.kill_unresponsive_apps,
        }

    def health_check(self) -> Dict:
        from windows.apps.manager import HAS_PYGETWINDOW

        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "window_state_control_available": HAS_PYGETWINDOW,
        }
