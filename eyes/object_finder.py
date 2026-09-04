"""
Object Finder
=============
No object-detection model is bundled in this project, so this module
does not pretend to classify *what* something is - it finds
*where the salient blobs are* via plain contour detection on an edge
map, then hands each blob back with only a generic label ("object")
plus its size/position. Same trade-off face_scanner.py makes with
aHash instead of a real embedding model: a working, honest pipeline
today beats a fake-precise one.

DISPLAY/price_tag.py is the intended consumer - it separately maps a
*name* the user has taught it (via a price_memory-style lookup, not
this module) onto whichever box the user points at, since this module
has no way to know a detected blob is "the blue mug" vs "the stapler".
"""

from typing import Dict, List, Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

MIN_AREA_FRACTION = 0.01  # ignore blobs smaller than 1% of frame area
MAX_OBJECTS = 20


class ObjectFinder:
    """Coarse contour-based blob localization. Use get_object_finder()."""

    def is_available(self) -> bool:
        return _CV2_AVAILABLE

    def find_objects(self, frame) -> List[Dict]:
        """Returns up to MAX_OBJECTS blobs as
        {"label": "object", "bbox": (x, y, w, h), "area_fraction": float},
        largest first. Empty list on no frame or backend unavailable."""
        if not self.is_available() or frame is None:
            return []
        try:
            h, w = frame.shape[:2]
            frame_area = h * w
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            edges = cv2.dilate(edges, None, iterations=2)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            results = []
            for c in contours:
                area = cv2.contourArea(c)
                fraction = area / frame_area if frame_area else 0
                if fraction < MIN_AREA_FRACTION:
                    continue
                x, y, bw, bh = cv2.boundingRect(c)
                results.append({"label": "object", "bbox": (x, y, bw, bh), "area_fraction": round(fraction, 4)})

            results.sort(key=lambda r: r["area_fraction"], reverse=True)
            return results[:MAX_OBJECTS]
        except Exception:
            return []


_object_finder: Optional[ObjectFinder] = None


def get_object_finder() -> ObjectFinder:
    global _object_finder
    if _object_finder is None:
        _object_finder = ObjectFinder()
    return _object_finder
