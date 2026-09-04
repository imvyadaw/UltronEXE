"""
Face Scanner
============
MEMORY/face_memory.py already does the naming half of face memory and
was written against a not-yet-built backend: `from
vision.face_recognition import get_embedding_id`, wrapped so any
failure - including the documented NotImplementedError - degrades to
"recognition unavailable". This module is that backend, finally built,
but it does NOT reproduce vision/face_recognition.py's import path
exactly (this project's vision code now lives under
eyes, not a bare `vision` package) - see the
compatibility shim at the bottom instead of silently renaming
face_memory.py's expectations.

No ML embedding model is bundled here, on purpose - same "cheap
heuristic over ML" call habit_memory.py and place_memory.py already
made. Detection uses OpenCV's bundled Haar cascade (ships with
opencv-python, no extra download); the "embedding" is a 64-bit average
hash (aHash) of the normalized, grayscale face crop. aHash is stable
across small lighting/angle changes but is NOT a real face-recognition
embedding - two different people can hash close together. Treat
recognize_live() results the way face_memory.py's own docstring
already tells callers to treat a None: a best guess, not a fact.
"""

from typing import List, Optional, Tuple

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

_CASCADE_NAME = "haarcascade_frontalface_default.xml"
_HASH_SIZE = 8  # 8x8 -> 64-bit hash


class FaceScanner:
    """Face detection + cheap perceptual-hash embeddings. Use get_face_scanner()."""

    def __init__(self):
        self._cascade = None
        if _CV2_AVAILABLE:
            try:
                path = cv2.data.haarcascades + _CASCADE_NAME
                self._cascade = cv2.CascadeClassifier(path)
                if self._cascade.empty():
                    self._cascade = None
            except Exception:
                self._cascade = None

    def is_available(self) -> bool:
        return _CV2_AVAILABLE and self._cascade is not None

    def detect_faces(self, frame) -> List[Tuple[int, int, int, int]]:
        """Returns a list of (x, y, w, h) boxes, largest first. Empty
        list on no detection, missing frame, or unavailable backend -
        never an exception."""
        if not self.is_available() or frame is None:
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            boxes = self._cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
            boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
            return [tuple(int(v) for v in b) for b in boxes]
        except Exception:
            return []

    def embedding_id(self, frame, box: Optional[Tuple[int, int, int, int]] = None) -> Optional[str]:
        """aHash of the largest detected face (or `box` if given) as a
        hex string. None if nothing to hash. Two calls on the same
        person's face in similar lighting should return the same or a
        very close string - close_match() below is the intended way to
        compare, not string equality, since lighting/angle drift is
        expected."""
        if not self.is_available() or frame is None:
            return None
        try:
            if box is None:
                boxes = self.detect_faces(frame)
                if not boxes:
                    return None
                box = boxes[0]
            x, y, w, h = box
            crop = frame[y : y + h, x : x + w]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (_HASH_SIZE, _HASH_SIZE))
            avg = small.mean()
            bits = (small > avg).flatten()
            value = 0
            for bit in bits:
                value = (value << 1) | int(bit)
            return format(value, f"0{_HASH_SIZE * _HASH_SIZE // 4}x")
        except Exception:
            return None

    @staticmethod
    def close_match(hash_a: str, hash_b: str, max_hamming: int = 10) -> bool:
        """Two embedding_ids are "the same person" if their Hamming
        distance is within max_hamming (out of 64 bits) - loose on
        purpose, this is a heuristic hash, not a trained metric.
        face_memory.recognize() itself still does exact string lookup;
        callers who want fuzzy matching (e.g. a future proactive/
        module) should compare via this instead of assuming
        recognize()'s exactness extends to noisy input."""
        try:
            a = int(hash_a, 16)
            b = int(hash_b, 16)
            return bin(a ^ b).count("1") <= max_hamming
        except Exception:
            return False


_face_scanner: Optional[FaceScanner] = None


def get_face_scanner() -> FaceScanner:
    global _face_scanner
    if _face_scanner is None:
        _face_scanner = FaceScanner()
    return _face_scanner


# -- compatibility shim for MEMORY/face_memory.py's recognize_live() ------
def get_embedding_id(frame) -> Optional[str]:
    """face_memory.recognize_live() imports `from
    vision.face_recognition import get_embedding_id`. That module
    doesn't exist in this project layout (this package is
    eyes.face_scanner, not a top-level
    `vision` package), so today that import still raises ImportError
    and recognize_live() still degrades to None exactly as documented.
    This function is the drop-in face_memory.py needs: either add a
    `vision/face_recognition.py` shim module that does
    `from eyes.face_scanner import get_embedding_id`,
    or update face_memory.py's import path directly. Left as a
    deliberate one-line follow-up rather than silently rewriting a
    module owned by Phase 18.2."""
    return get_face_scanner().embedding_id(frame)
