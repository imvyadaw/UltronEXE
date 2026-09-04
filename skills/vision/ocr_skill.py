"""
skills/vision/ocr_skill.py (Camera OCR skill facade)
=======================================================
Exposes CameraOCR (ocr_engine.py) through the common BaseSkill
interface, same pattern as camera_skill.py exposes VisionEngine.
Flattened directly under skills/vision/, not nested under an extra
skills/vision/skills/ subfolder - see skills/vision/__init__.py's
docstring for why that nested layout was already rejected once for
camera_skill.py; the same reasoning applies here.
"""

from typing import Dict

from skills.base_skill import BaseSkill
from skills.vision.ocr_engine import get_camera_ocr


class CameraOCRSkill(BaseSkill):
    """Physical-webcam text extraction via Tesseract - as opposed to
    read_screen_text, which OCRs a screenshot instead of the physical
    camera (a printed label, a page, a sign, etc.)."""

    name = "camera_ocr"
    description = "Read text visible to the physical camera right now, via Tesseract OCR."
    category = "perception"

    def __init__(self):
        self._ocr = get_camera_ocr()
        super().__init__()

    def register_actions(self) -> None:
        self._actions = {
            "read": self._ocr.read,
            "status": lambda: {"camera_available": self._ocr.is_available()},
        }

    def health_check(self) -> Dict:
        return {
            "success": True,
            "skill": self.name,
            "configured": True,
            "camera_available": self._ocr.is_available(),
        }
