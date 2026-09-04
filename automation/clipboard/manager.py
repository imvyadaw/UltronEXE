"""
Clipboard manager skill (Phase 5 facade)
===========================================
Wraps automation/clipboard/clipboard.py's ClipboardControl behind the
common BaseSkill interface used by the skill registry.
"""

from skills.base_skill import BaseSkill
from automation.clipboard.clipboard import ClipboardControl


class ClipboardManagerSkill(BaseSkill):
    """Read and write the system clipboard."""

    name = "clipboard_manager"
    description = "Read and write the system clipboard."
    category = "automation"

    def __init__(self):
        self._clipboard = ClipboardControl()
        super().__init__()

    def register_actions(self) -> None:
        c = self._clipboard
        self._actions = {
            "get": c.get_clipboard,
            "set": c.set_clipboard,
        }
