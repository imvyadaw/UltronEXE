"""
Text Reader
===========
A thin, honest wrapper over pytesseract - the one module in EYES/
that doesn't try to build a cheap heuristic replacement for the real
thing, because there isn't a sane one for OCR the way aHash stands in
for face embeddings. If pytesseract (and the underlying tesseract
binary) isn't installed, read_text() returns None, same contract as
every other optional-dependency module here.
"""

from typing import Optional

try:
    import pytesseract
    from PIL import Image
    import cv2

    _OCR_AVAILABLE = True
except Exception:
    _OCR_AVAILABLE = False


class TextReader:
    """OCR over a frame or region. Use get_text_reader()."""

    def is_available(self) -> bool:
        return _OCR_AVAILABLE

    def read_text(self, frame, region=None) -> Optional[str]:
        """region is an optional (x, y, w, h) to crop before OCR -
        pass the box from object_finder.find_objects() to read a label
        instead of a full scene. Returns stripped text, or None if
        nothing usable came back (blank frame, backend unavailable,
        empty OCR result all collapse to the same None)."""
        if not self.is_available() or frame is None:
            return None
        try:
            if region is not None:
                x, y, w, h = region
                frame = frame[y : y + h, x : x + w]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            text = pytesseract.image_to_string(image).strip()
            return text or None
        except Exception:
            return None


_text_reader: Optional[TextReader] = None


def get_text_reader() -> TextReader:
    global _text_reader
    if _text_reader is None:
        _text_reader = TextReader()
    return _text_reader
