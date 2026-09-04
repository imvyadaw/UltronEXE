"""
Mouse controller skill (Phase 5 facade)
==========================================
Wraps automation/mouse/mouse.py's MouseControl behind the common
BaseSkill interface used by the skill registry.
"""

from skills.base_skill import BaseSkill
from automation.mouse.mouse import MouseControl


class MouseControllerSkill(BaseSkill):
    """Move, click, drag, and scroll the mouse; query position and screen size."""

    name = "mouse_controller"
    description = "Move, click, double-click, drag, and scroll the mouse; read position/screen size."
    category = "automation"

    def __init__(self):
        self._mouse = MouseControl()
        super().__init__()

    def register_actions(self) -> None:
        m = self._mouse
        self._actions = {
            "move_to": m.move_to,
            "click": m.click,
            "double_click": m.double_click,
            "drag_to": m.drag_to,
            "scroll": m.scroll,
            "get_position": m.get_position,
            "get_screen_size": m.get_screen_size,
        }
