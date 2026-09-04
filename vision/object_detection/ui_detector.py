"""
UI object detector
====================
Finds *icon-only* clickable-looking UI elements (toolbar icons, close/
minimize buttons, unlabeled round buttons) - the gap vision/ui_detection/
element_locator.py openly documents it can't fill, since that module
only finds regions with OCR-readable text. This works purely on shape
and color-uniformity heuristics via OpenCV: small, roughly square or
circular contours with a mostly-uniform interior (an icon's flat fill or
glyph, not a photo or block of text) and a clear edge from their
surroundings are flagged as icon-button candidates. It's a heuristic,
not a trained UI-element classifier - expect some false positives on
busy/photographic screens, and treat the result as "worth a closer
look", not ground truth.
"""

from typing import Dict

try:
    import cv2
    import numpy as np

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from vision.screen.capture import ScreenCapture

# Icon-button candidates are small and roughly square/circular - real
# toolbar/tray icons are typically 16-64px, so this comfortably covers
# that range while excluding both tiny noise and full UI panels.
MIN_SIZE = 12
MAX_SIZE = 72
MIN_ASPECT = 0.6
MAX_ASPECT = 1.7
# How uniform the interior color has to be (lower std-dev = flatter
# fill = more icon-like, less like a photo/text block).
MAX_COLOR_STD = 45.0


class UIObjectDetector:
    """Detect icon-shaped, unlabeled UI elements via shape + color-
    uniformity heuristics (as opposed to element_locator.py's text-based
    detection)."""

    def __init__(self):
        self._screen = ScreenCapture()

    def find_icon_buttons(self, image=None) -> Dict:
        """Find candidate icon/button regions on a PIL Image, or the
        current screen if none given."""
        if not HAS_CV2:
            return {"error": "opencv-python not installed - run: pip install opencv-python-headless"}

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        try:
            rgb = np.array(image.convert("RGB"))
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

            candidates = []
            seen = set()
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if not (MIN_SIZE <= w <= MAX_SIZE and MIN_SIZE <= h <= MAX_SIZE):
                    continue
                aspect = w / h if h else 0
                if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
                    continue

                key = (x // 4, y // 4, w // 4, h // 4)
                if key in seen:
                    continue
                seen.add(key)

                patch = rgb[y : y + h, x : x + w]
                if patch.size == 0:
                    continue
                color_std = float(patch.reshape(-1, 3).std(axis=0).mean())
                if color_std > MAX_COLOR_STD:
                    continue

                shape = "circular" if 0.85 <= aspect <= 1.15 and self._is_round(contour, w, h) else "square"
                candidates.append(
                    {
                        "shape": shape,
                        "box": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                        "color_uniformity": round(1 - min(color_std / MAX_COLOR_STD, 1.0), 3),
                    }
                )

            return {"candidate_count": len(candidates), "icon_buttons": candidates}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _is_round(contour, w: int, h: int) -> bool:
        area = cv2.contourArea(contour)
        bbox_area = w * h
        if bbox_area == 0:
            return False
        # A filled circle covers ~78.5% of its bounding square; a filled
        # square covers ~100%. Anything meaningfully below that split is
        # "roundish" rather than a sharp-cornered square/rectangle.
        return (area / bbox_area) < 0.87


_instance: "UIObjectDetector" = None


def get_ui_object_detector() -> UIObjectDetector:
    global _instance
    if _instance is None:
        _instance = UIObjectDetector()
    return _instance
