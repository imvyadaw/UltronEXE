"""
skills/vision/ocr_engine.py
=============================
Camera-facing counterpart to vision/ocr/tesseract_ocr.py's
read_screen_text tool: same Tesseract OCR wrapper, run against a
physical-webcam frame (via camera_manager.py) instead of a screenshot.
Useful for reading text that only exists in the physical world - a
label, a page, a sign - as opposed to describe_screen/read_screen_text,
which read text rendered on the user's own display.

TesseractOCR already has a read_image(file_path) method built for
exactly this "existing image file on disk" case (its own docstring:
"screenshot, photo, scanned doc, etc."), so this module only adds the
camera-capture step in front of it - no OCR logic duplicated here.
"""

from typing import Optional

from skills.vision.camera_manager import get_camera_manager
from vision.ocr.tesseract_ocr import TesseractOCR


class CameraOCR:
    """Capture a frame from the physical camera and OCR it - read().
    Use get_camera_ocr()."""

    def __init__(self):
        self._camera = get_camera_manager()
        self._ocr = TesseractOCR()

    def is_available(self) -> bool:
        return self._camera.is_available()

    def read(self, lang: str = "eng") -> dict:
        """Returns {"success": True, "text": str, "char_count": int,
        "snapshot_path": str} or {"success": False, "error": str} -
        never raises (TesseractOCR.read_image() already fails soft;
        this just adds the capture step and the success flag)."""
        snapshot_path = self._camera.capture_snapshot()
        if snapshot_path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }
        result = self._ocr.read_image(snapshot_path, lang=lang)
        if result.get("error"):
            return {"success": False, "error": result["error"], "snapshot_path": snapshot_path}
        result["success"] = True
        result["snapshot_path"] = snapshot_path
        return result


_ocr_engine: Optional[CameraOCR] = None


def get_camera_ocr() -> CameraOCR:
    """Process-wide CameraOCR singleton, matching this codebase's
    get_x() convention."""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = CameraOCR()
    return _ocr_engine
