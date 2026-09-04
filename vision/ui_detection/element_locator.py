"""
UI element locator
====================
Locates on-screen text regions (word-level bounding boxes) via
pytesseract's image_to_data, on top of vision/ocr/tesseract_ocr.py's
engine. This finds *text-bearing* UI regions - buttons, labels, menu
items - by their text; for icon-only widgets with no label, see
vision/object_detection/ui_detector.py's shape/color-based detector
instead.
"""

from typing import Dict

try:
    import pytesseract

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

from vision.screen.capture import ScreenCapture

MIN_CONFIDENCE = 40


class ElementLocator:
    """Word-level text region detection on the screen, useful as a rough
    stand-in for "where are the clickable/readable things"."""

    def __init__(self):
        self._screen = ScreenCapture()

    def find_text_regions(self, image=None, min_confidence: int = MIN_CONFIDENCE) -> Dict:
        """Find bounding boxes of visible text on a PIL Image, or the
        current screen if none given."""
        if not HAS_OCR:
            return {
                "error": "pytesseract not installed - run: pip install pytesseract "
                "(and the Tesseract binary - see vision/ocr/tesseract_ocr.py's docstring)"
            }

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError:
            return {"error": "Tesseract binary not found on PATH - see vision/ocr/tesseract_ocr.py's docstring"}
        except Exception as e:
            return {"error": str(e)}

        regions = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            conf = int(float(data["conf"][i])) if data["conf"][i] not in ("-1", -1) else -1
            if not text or conf < min_confidence:
                continue
            regions.append(
                {
                    "text": text,
                    "confidence": conf,
                    "box": {
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "width": data["width"][i],
                        "height": data["height"][i],
                    },
                }
            )
        return {"region_count": len(regions), "regions": regions}


# Backwards-compatible alias for code written against the old
# vision/ui_detection/ui_detection.py module.
UIDetector = ElementLocator
