"""
YOLO object detector
=====================
General object detection via Ultralytics YOLOv8 (the free/open
"nano" checkpoint, yolov8n.pt - ~6MB, all 80 COCO classes: person, car,
dog, cat, laptop, cell phone, chair, tv, etc). This replaces the older
MobileNet-SSD detector this module used to ship - YOLOv8n is both more
accurate and covers 4x the classes (80 vs MobileNet-SSD's 20), at a
similar CPU-friendly speed.

    pip install ultralytics

The weights aren't bundled - ultralytics downloads and caches
yolov8n.pt itself on first use (same lazy-fetch approach every other
vision/ model-based module in this project takes), by default into the
current working directory unless YOLO_WEIGHTS_DIR below is set, in
which case it's downloaded there instead.
"""

from pathlib import Path
from typing import Dict

from vision.screen.capture import ScreenCapture
from config import CACHE_DIR
from stability.lazy_loader import lazy_module

# PHASE 29-A stability fix: `from ultralytics import YOLO` used to sit at
# module level (inside a try/except, but the import attempt - and
# ultralytics' own `import torch` - still ran the moment this module was
# imported). Since windows/__init__.py imports this module eagerly,
# `import windows` used to always pay torch's import cost (commonly 1-3s
# cold) even for tool calls that never touch vision. `_ultralytics` below
# only actually imports on first `.get()`/`.available` call, i.e. the first
# real detect() - see stability/lazy_loader.py.
_ultralytics = lazy_module("ultralytics")

YOLO_WEIGHTS_DIR = Path(CACHE_DIR) / "models"
YOLO_WEIGHTS_PATH = YOLO_WEIGHTS_DIR / "yolov8n.pt"
YOLO_MODEL_NAME = "yolov8n.pt"


class YOLODetector:
    """80-class (COCO) object detection via YOLOv8n."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._model = None

    def _get_model(self):
        if self._model is None:
            YOLO_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
            YOLO = _ultralytics.get(strict=True).YOLO
            # Passing the target path both lets ultralytics reuse an
            # already-downloaded checkpoint and controls where a fresh
            # download lands, instead of littering the working directory.
            model_path = YOLO_WEIGHTS_PATH if YOLO_WEIGHTS_PATH.exists() else YOLO_MODEL_NAME
            self._model = YOLO(str(model_path))
            if not YOLO_WEIGHTS_PATH.exists():
                # First run downloaded yolov8n.pt into the cwd - move it
                # into the cache dir so future runs find it there instead.
                cwd_copy = Path.cwd() / YOLO_MODEL_NAME
                if cwd_copy.exists():
                    try:
                        cwd_copy.replace(YOLO_WEIGHTS_PATH)
                    except Exception:
                        from core.error_trace import log_swallowed as _lsw

                        _lsw("vision.object_detection.yolo_detector._get_model")
        return self._model

    def detect(self, image=None, confidence_threshold: float = 0.4) -> Dict:
        """Detect objects in a PIL Image, or the current screen if none given."""
        if not _ultralytics.available:
            return {"error": "ultralytics not installed - run: pip install ultralytics"}

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        try:
            model = self._get_model()
            results = model.predict(source=image, conf=confidence_threshold, verbose=False)
            result = results[0]

            objects = []
            for box in result.boxes:
                x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
                class_id = int(box.cls[0])
                objects.append(
                    {
                        "label": result.names.get(class_id, str(class_id)),
                        "confidence": round(float(box.conf[0]), 3),
                        "box": {
                            "x": int(x1),
                            "y": int(y1),
                            "width": int(x2 - x1),
                            "height": int(y2 - y1),
                        },
                    }
                )
            return {"object_count": len(objects), "objects": objects}
        except Exception as e:
            return {"error": str(e)}


_instance: "YOLODetector" = None


def get_yolo_detector() -> YOLODetector:
    global _instance
    if _instance is None:
        _instance = YOLODetector()
    return _instance


# Backwards-compatible alias for code written against the old
# MobileNet-SSD-backed ObjectDetector class in this module.
ObjectDetector = YOLODetector
