"""
skills/vision/scene_skill.py (Camera scene-analysis skill facade)
=====================================================================
Exposes SceneAnalyzer (scene_analyzer.py) through the common BaseSkill
interface, same pattern as camera_skill.py exposes VisionEngine.
Flattened directly under skills/vision/, not nested under an extra
skills/vision/skills/ subfolder - see skills/vision/__init__.py's
docstring for why that nested layout was already rejected once for
camera_skill.py; the same reasoning applies here.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.vision.scene_analyzer import get_scene_analyzer


class CameraSceneSkill(BaseSkill):
    """Combined physical-webcam scene understanding: description +
    object detection + OCR from one capture, for when a caller wants
    the fuller picture rather than calling vision/camera_object_detection/
    camera_ocr separately (and risking three different moments)."""

    name = "camera_scene"
    description = (
        "Analyze what the physical camera currently sees: description, objects, and any visible text, from one capture."
    )
    category = "perception"

    def __init__(self):
        self._analyzer = get_scene_analyzer()
        super().__init__()

    def register_actions(self) -> None:
        self._actions = {
            "analyze": self._analyzer.analyze,
            "status": lambda: {"camera_available": self._analyzer.is_available()},
        }

    def health_check(self) -> Dict:
        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "camera_available": self._analyzer.is_available(),
        }
