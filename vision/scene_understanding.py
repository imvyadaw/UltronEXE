"""
Scene understanding
====================
A synthesis layer on top of the vision/ modules that already exist
(vision/ocr, vision/object_detection, vision/image_analysis) rather than
a new detection model of its own - there's no bundled general-purpose
"describe this scene" model in this project, so this answers "what's on
my screen right now" by combining what the existing detectors already
see: visible text (OCR), general objects (MobileNet-SSD, useful mostly
for a webcam/photo, not much fires on a typical desktop screenshot), and
basic image stats (brightness/dominant colors) - then buckets the OCR
text by screen region (top/bottom/left/right/center) so a caller gets a
rough layout, not just an unordered word soup.
"""

from typing import Dict, List

from vision.screen.capture import ScreenCapture
from vision.ocr.tesseract_ocr import OCR
from vision.object_detection.yolo_detector import ObjectDetector
from vision.image_analysis.analyzer import ImageAnalyzer
from vision.ui_detection.element_locator import UIDetector


def _bucket_region(box: Dict, width: int, height: int) -> str:
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    col = "left" if cx < width / 3 else ("right" if cx > 2 * width / 3 else "center")
    row = "top" if cy < height / 3 else ("bottom" if cy > 2 * height / 3 else "middle")
    if row == "middle" and col == "center":
        return "center"
    return f"{row}-{col}"


class SceneUnderstanding:
    """Combine OCR + object detection + image stats into one "what am I
    looking at" summary, instead of the caller having to run and merge
    three separate tools by hand."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._ocr = OCR()
        self._ui = UIDetector()
        self._objects = ObjectDetector()
        self._image = ImageAnalyzer()

    def describe_screen(self, include_objects: bool = True, max_text_regions: int = 40) -> Dict:
        """Capture the current screen once and run every available
        detector against that single capture (cheaper and more
        consistent than each tool grabbing its own separate screenshot)."""
        image = self._screen.capture()
        if isinstance(image, dict):
            return image

        stats = self._image.analyze(image=image)
        if "error" in stats:
            return stats

        regions_result = self._ui.find_text_regions(image=image)
        text_regions = regions_result.get("regions", []) if "error" not in regions_result else []

        layout: Dict[str, List[str]] = {}
        for region in text_regions[:max_text_regions]:
            bucket = _bucket_region(region["box"], stats["width"], stats["height"])
            layout.setdefault(bucket, []).append(region["text"])

        summary = {
            "resolution": {"width": stats["width"], "height": stats["height"]},
            "is_mostly_dark": stats["is_mostly_dark"],
            "dominant_colors": stats["dominant_colors"],
            "text_region_count": len(text_regions),
            "text_by_layout_region": layout,
            "full_text_preview": " ".join(r["text"] for r in text_regions[:15]),
        }

        if include_objects:
            objects_result = self._objects.detect(image=image)
            summary["objects"] = objects_result.get("objects", []) if "error" not in objects_result else []
            if "error" in objects_result:
                summary["objects_note"] = objects_result["error"]

        return summary


_instance: "SceneUnderstanding" = None


def get_scene_understanding() -> SceneUnderstanding:
    global _instance
    if _instance is None:
        _instance = SceneUnderstanding()
    return _instance
