"""
Browser automation skill (Phase 4 facade)
==========================================
Wraps browser/automation/automation.py's browser-agnostic controls (which
auto-detect whichever of Chrome/Edge/Firefox is active) behind the common
BaseSkill interface used by the skill registry / AI tool layer.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from browser.automation.automation import BrowserAutomation as _CoreBrowserAutomation


class BrowserAutomationSkill(BaseSkill):
    """Scroll, navigate, type, zoom, and manage tabs in whichever browser is active."""

    name = "browser_automation"
    description = "Scroll, navigate, type, zoom, and manage tabs in the active browser (auto-detected)."
    category = "browser"

    def __init__(self):
        self._core = _CoreBrowserAutomation()
        super().__init__()

    def register_actions(self) -> None:
        c = self._core
        self._actions = {
            "detect_browser": c.detect_active_browser,
            "scroll": c.browser_scroll,
            "navigate": c.browser_navigate,
            "type": c.browser_type,
            "zoom": c.browser_zoom,
            "list_tabs": c.list_tabs,
            "close_tab": c.close_tab,
        }

    def health_check(self) -> Dict:
        from browser.automation.automation import HAS_PYGETWINDOW

        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "active_browser_detection_available": HAS_PYGETWINDOW,
        }
