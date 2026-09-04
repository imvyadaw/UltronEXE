"""
Macro player skill (Phase 5 facade)
=====================================
Playback-side actions of automation/macro/macro.py's MacroRecorder
(replay a saved macro via pyautogui, list what's available) behind the
common BaseSkill interface. Recording lives in the sibling
automation/macro/recorder.py.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from automation.macro.macro import MacroRecorder


class MacroPlayerSkill(BaseSkill):
    """Replay a previously recorded macro, optionally faster or slower than real time."""

    name = "macro_player"
    description = "Play back a saved macro (mouse clicks + key presses) at any speed."
    category = "automation"

    def __init__(self):
        self._player = MacroRecorder()
        super().__init__()

    def register_actions(self) -> None:
        p = self._player
        self._actions = {
            "play": p.play_macro,
            "list": p.list_macros,
        }

    def health_check(self) -> Dict:
        from automation.macro.macro import HAS_PYAUTOGUI

        return {"success": True, "skill": self.name, "configured": HAS_PYAUTOGUI}
