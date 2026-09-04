"""
Form recognition
=================
Heuristic detection of form-like UI elements on screen - text input
boxes and checkboxes - via OpenCV contour geometry (no trained
form-detection model is bundled with this project), then pairs each
detected field with whatever OCR'd text sits immediately to its left or
above it as a best-guess label ("Email:", "Subscribe", etc). Good enough
to answer "what fields are on this form" or "is there a checkbox near
the word X"; it will miss custom-styled/borderless fields since it's
looking for rectangle edges, not a semantic understanding of the page.
"""

from typing import Dict, List

try:
    import cv2
    import numpy as np

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from vision.screen.capture import ScreenCapture
from vision.ui_detection.element_locator import UIDetector

# Aspect-ratio / size heuristics for classifying a detected rectangle.
CHECKBOX_MAX_SIZE = 30  # roughly-square boxes this small or smaller
TEXT_FIELD_MIN_ASPECT = 2.5  # width / height - text inputs are wide and short
MIN_AREA = 150
MAX_LABEL_DISTANCE = 160  # pixels - how far a label can be and still "belong" to a field


class FormRecognizer:
    """Detect input-box/checkbox-shaped rectangles on screen and label
    them using nearby OCR'd text."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._ui = UIDetector()

    def _nearest_label(self, box: Dict, text_regions: List[Dict]) -> str:
        fx, fy = box["x"], box["y"] + box["height"] / 2
        best, best_dist = None, MAX_LABEL_DISTANCE
        for region in text_regions:
            rb = region["box"]
            # Prefer labels to the left of, or directly above, the field -
            # the two overwhelmingly common form layouts.
            rx, ry = rb["x"] + rb["width"], rb["y"] + rb["height"] / 2
            to_left = fx - rx
            above = box["y"] - (rb["y"] + rb["height"])
            if 0 <= to_left <= MAX_LABEL_DISTANCE and abs(ry - fy) < 20:
                dist = to_left
            elif 0 <= above <= MAX_LABEL_DISTANCE and abs((rb["x"]) - box["x"]) < MAX_LABEL_DISTANCE:
                dist = above
            else:
                continue
            if dist < best_dist:
                best, best_dist = region["text"], dist
        return best

    def detect_fields(self, image=None) -> Dict:
        """Find candidate text-input and checkbox rectangles on a PIL
        Image, or the current screen if none given, each paired with its
        best-guess nearby label."""
        if not HAS_CV2:
            return {"error": "opencv-python not installed - run: pip install opencv-python-headless"}

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        text_result = self._ui.find_text_regions(image=image)
        text_regions = text_result.get("regions", []) if "error" not in text_result else []

        try:
            frame = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 40, 120)
            edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            fields = []
            seen_boxes = set()
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                if area < MIN_AREA:
                    continue
                key = (x // 4, y // 4, w // 4, h // 4)  # de-dupe near-identical nested contours
                if key in seen_boxes:
                    continue
                seen_boxes.add(key)

                aspect = w / h if h else 0
                box = {"x": x, "y": y, "width": w, "height": h}

                if w <= CHECKBOX_MAX_SIZE and h <= CHECKBOX_MAX_SIZE and 0.7 <= aspect <= 1.4:
                    field_type = "checkbox"
                elif aspect >= TEXT_FIELD_MIN_ASPECT and 18 <= h <= 60 and w >= 60:
                    field_type = "text_field"
                else:
                    continue

                fields.append(
                    {
                        "type": field_type,
                        "box": box,
                        "label": self._nearest_label(box, text_regions),
                    }
                )

            return {"field_count": len(fields), "fields": fields}
        except Exception as e:
            return {"error": str(e)}


_instance: "FormRecognizer" = None


def get_form_recognizer() -> FormRecognizer:
    global _instance
    if _instance is None:
        _instance = FormRecognizer()
    return _instance
