"""
UI element finder skill (Phase 5 facade)
===========================================
Wraps automation/ui/ui_automation.py's UIAutomation (pywinauto-backed
find/click/type/list of on-screen UI controls, plus window activation)
behind the common BaseSkill interface used by the skill registry.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from automation.ui.ui_automation import UIAutomation


class ElementFinderSkill(BaseSkill):
    """Find, click, and type into named UI elements inside application windows."""

    name = "ui_element_finder"
    description = "Find, click, and type into UI elements (buttons, fields, etc.) inside app windows."
    category = "automation"

    def __init__(self):
        self._ui = UIAutomation()
        super().__init__()

    def register_actions(self) -> None:
        u = self._ui
        self._actions = {
            "find_element": u.find_element,
            "click_element": u.click_element,
            "activate_window": u.activate_window,
            "type_into_element": u.type_into_element,
            "list_elements": u.list_elements,
        }

    def health_check(self) -> Dict:
        try:
            from automation.ui.ui_automation import HAS_PYWINAUTO

            configured = HAS_PYWINAUTO
        except ImportError:
            configured = True  # module doesn't gate behind an availability flag
        return {"success": True, "skill": self.name, "configured": configured}
