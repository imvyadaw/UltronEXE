"""
Handwriting recognition
========================
No handwriting-specific model is bundled with this project. This uses
vision/ocr/easyocr_ocr.py (a general OCR model that handles handwritten/
cursive text, and Hindi/Devanagari, far better than Tesseract) when
EasyOCR is installed, and otherwise falls back to vision/ocr/tesseract_ocr.py
with a config tuned for single blocks of freeform text (--psm 6) - which
works passably on neat print handwriting and poorly on cursive, so the
fallback result is flagged with a confidence caveat instead of silently
pretending it's reliable.
"""

from typing import Dict, Optional, Sequence

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract

    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

from vision.screen.capture import ScreenCapture
from vision.ocr.easyocr_ocr import EasyOCROCR, HAS_EASYOCR, DEFAULT_LANGUAGES

HANDWRITING_PSM_CONFIG = "--psm 6"  # "assume a single uniform block of text"


class HandwritingRecognizer:
    """Read handwritten text from an image, preferring EasyOCR (better
    accuracy on handwriting, plus Hindi) and falling back to a tuned
    Tesseract pass."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._easyocr = EasyOCROCR() if HAS_EASYOCR else None

    def _read_with_tesseract(self, image) -> Dict:
        try:
            text = pytesseract.image_to_string(image, config=HANDWRITING_PSM_CONFIG).strip()
            return {
                "engine": "tesseract",
                "text": text,
                "word_count": len(text.split()),
                "note": "Tesseract is tuned for printed text - handwriting/cursive accuracy is "
                "unreliable. Install EasyOCR (pip install easyocr) for better results.",
            }
        except Exception as e:
            return {"error": str(e)}

    def read(self, image=None, file_path: Optional[str] = None, languages: Sequence[str] = DEFAULT_LANGUAGES) -> Dict:
        """Read handwritten text from a PIL Image, an image file path, or
        (if neither given) the current screen."""
        if file_path:
            if not HAS_PIL:
                return {"error": "Pillow not installed - run: pip install Pillow"}
            try:
                image = Image.open(file_path)
            except Exception as e:
                return {"error": str(e)}
        elif image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        if self._easyocr is not None:
            return self._easyocr._run_ocr(image, languages)
        if HAS_TESSERACT:
            return self._read_with_tesseract(image)
        return {
            "error": "No OCR engine available - run: pip install easyocr  (recommended for "
            "handwriting), or at least: pip install pytesseract Pillow"
        }


_instance: "HandwritingRecognizer" = None


def get_handwriting_recognizer() -> HandwritingRecognizer:
    global _instance
    if _instance is None:
        _instance = HandwritingRecognizer()
    return _instance
