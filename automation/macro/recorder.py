"""
Macro recorder skill (Phase 5 facade)
=======================================
Recording-side actions of automation/macro/macro.py's MacroRecorder
(start/stop capturing real mouse+keyboard input via pynput, plus
list/delete of saved macros) behind the common BaseSkill interface.
Playback lives in the sibling automation/macro/player.py - both wrap the
same MacroRecorder class, which reads/writes macro JSON files on every
call, so a recorder instance and a player instance never need to be the
literal same object to stay in sync.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from automation.macro.macro import MacroRecorder


class MacroRecorderSkill(BaseSkill):
    """Start/stop capturing mouse+keyboard input as a named, replayable macro."""

    name = "macro_recorder"
    description = "Record real mouse clicks and key presses into a named, saved macro."
    category = "automation"

    def __init__(self):
        self._recorder = MacroRecorder()
        super().__init__()

    def register_actions(self) -> None:
        r = self._recorder
        self._actions = {
            "start": r.start_recording,
            "stop": r.stop_recording,
            "list": r.list_macros,
            "delete": r.delete_macro,
        }

    def health_check(self) -> Dict:
        from automation.macro.macro import HAS_PYNPUT

        return {"success": True, "skill": self.name, "configured": HAS_PYNPUT}
