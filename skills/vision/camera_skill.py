"""
skills/vision/camera_skill.py (Camera+vision skill facade)
=============================================================
Exposes VisionEngine (vision_engine.py) through the common BaseSkill
interface, same pattern as skills/app_control/controller.py exposes
AppControlManager: no camera/vision logic here, just the
execute("see"/"snapshot"/"status") entry point the skill registry
(skills/__init__.py) expects.

Reachable two ways, matching how every other real capability in this
project ends up actually callable:
  - skills.get_skill("vision") / skills.execute_skill("vision", ...)
  - the AI tool-calling loop, via ai/vision_skill_tools.py's
    camera_see/camera_snapshot/camera_status tools (registered in
    ai/tools_schema.py + ai/tool_runtime.py) - these call VisionEngine
    directly rather than round-tripping through this facade, the same
    choice ai/vision_agent_tools.py already made for VisionAgent.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.vision.vision_engine import get_vision_engine


class VisionSkill(BaseSkill):
    """Physical-webcam capture + description (as opposed to screen
    capture, which skills/utilities and the Vision:OCR tool group
    already cover)."""

    name = "vision"
    description = "See through the physical camera - capture and describe what it currently sees."
    category = "perception"

    def __init__(self):
        self._engine = get_vision_engine()
        super().__init__()

    def register_actions(self) -> None:
        e = self._engine
        self._actions = {
            "see": e.see,
            "snapshot": e.snapshot,
            "status": e.status,
        }

    def health_check(self) -> Dict:
        status = self._engine.status()
        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            **status,
        }
