"""
Keyboard controller skill (Phase 5 facade)
=============================================
Wraps automation/keyboard/keyboard.py's KeyboardControl behind the
common BaseSkill interface used by the skill registry.
"""

from skills.base_skill import BaseSkill
from automation.keyboard.keyboard import KeyboardControl


class KeyboardControllerSkill(BaseSkill):
    """Type text and press individual keys/key combos."""

    name = "keyboard_controller"
    description = "Type text and press individual keys or key combinations."
    category = "automation"

    def __init__(self):
        self._keyboard = KeyboardControl()
        super().__init__()

    def register_actions(self) -> None:
        k = self._keyboard
        self._actions = {
            "type_text": k.type_text,
            "press_key": k.press_key,
        }
