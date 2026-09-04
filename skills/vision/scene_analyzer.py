"""
skills/vision/scene_analyzer.py
=================================
Camera-facing counterpart to agents/vision_agent.py's VisionAgent.see()
(which runs OCR + faces + objects + UI regions against one screen
capture) - but for the physical webcam: one camera_manager.py capture,
then vision_engine.py's description (local/remote) + object_detector.py's
YOLO detection + ocr_engine.py's Tesseract OCR against that SAME frame,
so all three results describe one consistent moment instead of three
separate (and possibly different) camera captures.

Deliberately thin: no description/detection/OCR logic lives here, only
the "capture once, fan out to three already-existing engines, merge the
results" sequencing - the same division of responsibility
vision_engine.py already uses for camera_manager.py + vision_provider.py.
"""

from typing import Optional

from skills.vision.camera_manager import get_camera_manager
from skills.vision.vision_provider import get_vision_provider
from skills.vision.remote_vision_provider import get_remote_vision_provider
from vision.object_detection.yolo_detector import get_yolo_detector
from vision.ocr.tesseract_ocr import TesseractOCR


class SceneAnalyzer:
    """Capture one camera frame and run description + object detection +
    OCR against it together - analyze(). Use get_scene_analyzer()."""

    def __init__(self):
        self._camera = get_camera_manager()
        self._local = get_vision_provider()
        self._remote = get_remote_vision_provider()
        self._yolo = get_yolo_detector()
        self._ocr = TesseractOCR()

    def is_available(self) -> bool:
        return self._camera.is_available()

    def analyze(self, prompt: Optional[str] = None, confidence_threshold: float = 0.4) -> dict:
        """Returns {"success": True, "snapshot_path": str,
        "description": {...}, "objects": {...}, "text": {...}} -
        each sub-result keeps its own success/error so a caller can tell
        exactly which of the three failed without the whole call failing.
        Only returns {"success": False, ...} outright if the camera
        capture itself fails - never raises."""
        snapshot_path = self._camera.capture_snapshot()
        if snapshot_path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }

        description = self._describe(snapshot_path, prompt)
        objects = self._detect_objects(snapshot_path, confidence_threshold)
        text = self._read_text(snapshot_path)

        return {
            "success": True,
            "snapshot_path": snapshot_path,
            "description": description,
            "objects": objects,
            "text": text,
        }

    def _describe(self, snapshot_path: str, prompt: Optional[str]) -> dict:
        if self._local.is_available():
            result = self._local.describe(snapshot_path, prompt=prompt)
            if result.get("success"):
                result["backend"] = "local"
                return result
        if self._remote.is_available():
            result = self._remote.describe(snapshot_path, prompt=prompt)
            if result.get("success"):
                result["backend"] = "remote"
                return result
            return result
        return {"success": False, "error": "No vision backend available for description."}

    def _detect_objects(self, snapshot_path: str, confidence_threshold: float) -> dict:
        result = self._yolo.detect(image=snapshot_path, confidence_threshold=confidence_threshold)
        if result.get("error"):
            return {"success": False, "error": result["error"]}
        result["success"] = True
        return result

    def _read_text(self, snapshot_path: str) -> dict:
        result = self._ocr.read_image(snapshot_path)
        if result.get("error"):
            return {"success": False, "error": result["error"]}
        result["success"] = True
        return result


_analyzer: Optional[SceneAnalyzer] = None


def get_scene_analyzer() -> SceneAnalyzer:
    """Process-wide SceneAnalyzer singleton, matching this codebase's
    get_x() convention."""
    global _analyzer
    if _analyzer is None:
        _analyzer = SceneAnalyzer()
    return _analyzer
