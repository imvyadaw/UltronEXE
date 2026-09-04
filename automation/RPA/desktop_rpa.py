"""
Desktop RPA skill (Phase 5 facade)
=====================================
Combines the three existing RPA modules - automation/RPA/recorder.py
(RPARecorder: capture mouse/keyboard as an editable step list),
automation/RPA/player.py (RPAPlayer: play/dry-run a saved script), and
automation/RPA/editor.py (RPAEditor: CRUD on individual steps) - behind
one BaseSkill interface for desktop-based robotic process automation.
Browser-based RPA lives in the sibling automation/RPA/web_rpa.py.
"""

from skills.base_skill import BaseSkill
from automation.RPA.recorder import RPARecorder
from automation.RPA.player import RPAPlayer
from automation.RPA.editor import RPAEditor


class DesktopRPASkill(BaseSkill):
    """Record, edit, and play back desktop automation scripts (mouse/keyboard/UI steps)."""

    name = "desktop_rpa"
    description = "Record, edit, and play back desktop RPA scripts made of mouse/keyboard/UI steps."
    category = "automation"

    def __init__(self):
        self._recorder = RPARecorder()
        self._player = RPAPlayer()
        self._editor = RPAEditor()
        super().__init__()

    def register_actions(self) -> None:
        rec, play, ed = self._recorder, self._player, self._editor
        self._actions = {
            # recording
            "start_recording": rec.start_recording,
            "pause_recording": rec.pause_recording,
            "resume_recording": rec.resume_recording,
            "add_step": rec.add_step,
            "stop_recording": rec.stop_recording,
            "discard_recording": rec.discard_recording,
            # playback
            "play": play.play,
            "dry_run": play.dry_run,
            # editing / CRUD
            "create_script": ed.create_script,
            "load_script": ed.load,
            "list_scripts": ed.list_scripts,
            "insert_step": ed.insert_step,
            "update_step": ed.update_step,
            "delete_step": ed.delete_step,
            "reorder_steps": ed.reorder_steps,
            "delete_script": ed.delete_script,
            "rename_step_type": ed.rename_step_type,
        }
