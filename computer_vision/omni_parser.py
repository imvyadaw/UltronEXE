"""
Omni parser
=============
Merges vision/ui_detection/element_locator.py's text regions (word-level
OCR boxes) and vision/object_detection/ui_detector.py's icon/button
candidates (shape/color-based, for icon-only widgets with no label) into
one flat, indexed list of screen elements - an OmniParser-style unified
parse of "everything that looks interactable on this screen", built on
one shared screenshot so every element's coordinates line up.

Each element gets a stable-for-this-parse integer `id` so downstream
modules (screen_grounding.py, visual_automator.py) can refer to
"element 7" instead of re-describing a box every time. Nothing here
classifies *what kind* of element something is (button vs. text field
vs. label) - that's ui_element_detector.py's job, layered on top of this
module's raw merge so the two concerns (parsing vs. classifying) stay
separable, same as vision/scene_understanding.py keeping OCR/objects/
image-stats as separate calls it then combines.
"""

from typing import Dict, List, Optional

from vision.screen.capture import ScreenCapture
from vision.ui_detection.element_locator import ElementLocator
from vision.object_detection.ui_detector import UIObjectDetector
from core.logger import get_logger

logger = get_logger("ultron.interaction.omni_parser")


def _boxes_overlap(a: Dict, b: Dict) -> bool:
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    return not (ax2 <= b["x"] or bx2 <= a["x"] or ay2 <= b["y"] or by2 <= a["y"])


class OmniParser:
    """Parses one screenshot into a flat list of {id, kind, text, box,
    center} elements. One shared ScreenCapture instance so `parse()`'s
    single grab feeds both underlying detectors consistently."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._text_locator = ElementLocator()
        self._icon_detector = UIObjectDetector()

    def parse(self, image=None, min_confidence: int = 40) -> Dict:
        """Run the full merge. Returns {"element_count", "elements",
        "screen_size"} or {"error": ...}."""
        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        text_result = self._text_locator.find_text_regions(image, min_confidence=min_confidence)
        icon_result = self._icon_detector.find_icon_buttons(image)

        elements: List[Dict] = []
        eid = 0

        text_regions = text_result.get("regions", []) if isinstance(text_result, dict) else []
        for region in text_regions:
            elements.append(
                {
                    "id": eid,
                    "kind": "text",
                    "text": region["text"],
                    "confidence": region.get("confidence"),
                    "box": region["box"],
                    "center": self._center(region["box"]),
                }
            )
            eid += 1

        icon_boxes = icon_result.get("icon_buttons", []) if isinstance(icon_result, dict) else []
        for icon in icon_boxes:
            box = icon["box"]
            # Skip icon candidates that just re-detect a text region we
            # already have (e.g. a text label's bounding box also
            # tripped the edge-contour icon detector) - keep the text
            # element, since it carries more information (the label).
            if any(el["kind"] == "text" and _boxes_overlap(el["box"], box) for el in elements):
                continue
            elements.append(
                {
                    "id": eid,
                    "kind": "icon",
                    "text": None,
                    "shape": icon.get("shape"),
                    "confidence": icon.get("color_uniformity"),
                    "box": box,
                    "center": self._center(box),
                }
            )
            eid += 1

        width, height = image.size if hasattr(image, "size") else (None, None)
        return {
            "element_count": len(elements),
            "elements": elements,
            "screen_size": {"width": width, "height": height},
        }

    @staticmethod
    def _center(box: Dict) -> Dict:
        return {"x": box["x"] + box["width"] // 2, "y": box["y"] + box["height"] // 2}


_parser: Optional[OmniParser] = None


def get_omni_parser() -> OmniParser:
    global _parser
    if _parser is None:
        _parser = OmniParser()
    return _parser
