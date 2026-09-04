"""
skills/vision/object_detection_skill.py (Camera object-detection skill facade)
=================================================================================
Exposes CameraObjectDetector (object_detector.py) through the common
BaseSkill interface, same pattern as camera_skill.py exposes
VisionEngine. Flattened directly under skills/vision/, not nested
under an extra skills/vision/skills/ subfolder - see skills/vision/
__init__.py's docstring for why that nested layout was already rejected
once for camera_skill.py; the same reasoning applies here.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.vision.object_detector import get_camera_object_detector


class CameraObjectDetectionSkill(BaseSkill):
    """Physical-webcam object detection (80 COCO classes via YOLOv8n) -
    as opposed to detect_objects_on_screen, which detects objects in a
    screenshot instead of the physical camera."""

    name = "camera_object_detection"
    description = "Detect objects visible to the physical camera right now (80 COCO classes via YOLOv8n)."
    category = "perception"

    def __init__(self):
        self._detector = get_camera_object_detector()
        super().__init__()

    def register_actions(self) -> None:
        self._actions = {
            "detect": self._detector.detect,
            "status": lambda: {"camera_available": self._detector.is_available()},
        }

    def health_check(self) -> Dict:
        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "camera_available": self._detector.is_available(),
        }
