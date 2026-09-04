"""
skills/vision/object_detector.py
==================================
Camera-facing counterpart to vision/object_detection/yolo_detector.py's
detect_objects_on_screen tool: same 80-class YOLOv8n model, but run
against a physical-webcam frame (via camera_manager.py) instead of a
screenshot (via vision/screen/capture.py's ScreenCapture).

No detection logic lives here - YOLODetector.detect() already accepts
an `image` argument (falls back to a screen capture only when it's
None), so this module just supplies a camera snapshot path instead and
delegates everything else. Mirrors vision_provider.py's relationship to
models/vision/model_manager.py: a thin camera-input adapter over an
already-existing, already-tested model wrapper, not a second model
implementation.
"""

from typing import Optional

from skills.vision.camera_manager import get_camera_manager
from vision.object_detection.yolo_detector import get_yolo_detector


class CameraObjectDetector:
    """Capture a frame from the physical camera and run YOLOv8n object
    detection on it - detect(). Use get_camera_object_detector()."""

    def __init__(self):
        self._camera = get_camera_manager()
        self._yolo = get_yolo_detector()

    def is_available(self) -> bool:
        return self._camera.is_available()

    def detect(self, confidence_threshold: float = 0.4) -> dict:
        """Returns {"success": True, "object_count": int, "objects": [...],
        "snapshot_path": str} or {"success": False, "error": str} -
        never raises (YOLODetector.detect() already fails soft; this
        just adds the capture step and the success flag)."""
        snapshot_path = self._camera.capture_snapshot()
        if snapshot_path is None:
            return {
                "success": False,
                "error": "Could not capture a camera frame - no webcam available or opencv not installed.",
            }
        result = self._yolo.detect(image=snapshot_path, confidence_threshold=confidence_threshold)
        if result.get("error"):
            return {"success": False, "error": result["error"], "snapshot_path": snapshot_path}
        result["success"] = True
        result["snapshot_path"] = snapshot_path
        return result


_detector: Optional[CameraObjectDetector] = None


def get_camera_object_detector() -> CameraObjectDetector:
    """Process-wide CameraObjectDetector singleton, matching this
    codebase's get_x() convention."""
    global _detector
    if _detector is None:
        _detector = CameraObjectDetector()
    return _detector
