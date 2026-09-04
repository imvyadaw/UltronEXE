"""
skills/vision/change_detection_skill.py (Camera change-detection skill facade)
=================================================================================
Exposes ChangeDetector (change_detector.py) through the common BaseSkill
interface, same pattern as camera_skill.py exposes VisionEngine.

Flattened directly under skills/vision/, NOT nested under
skills/vision/skills/ (the structure this feature was originally
requested with) - skills/vision/__init__.py's docstring already
documents that a nested skills/vision/skills/ layout was considered and
rejected twice for the other camera facades, and none of them (or any
other category under skills/) nest a second skills/ folder inside their
own. Same reasoning applies here, so this stays flat and consistent.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.vision.change_detector import get_change_detector


class ChangeDetectionSkill(BaseSkill):
    """Physical-webcam change detection: remembers a baseline frame and
    reports whether the scene has changed since - "did anything change
    while I was away/not looking"."""

    name = "camera_change_detection"
    description = "Detect whether the physical camera's view has changed since a baseline was set."
    category = "perception"

    def __init__(self):
        self._detector = get_change_detector()
        super().__init__()

    def register_actions(self) -> None:
        d = self._detector
        self._actions = {
            "set_baseline": d.set_baseline,
            "check": d.check,
            "status": d.status,
            "history": d.history,
            "clear": d.clear,
        }

    def health_check(self) -> Dict:
        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "camera_available": self._detector.is_available(),
        }
