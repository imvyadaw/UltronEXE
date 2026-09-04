"""
EasyOCR
=======
Text extraction via EasyOCR - a neural OCR model that handles
handwriting, stylized fonts, and non-Latin scripts (Devanagari/Hindi
included) far better than Tesseract, at the cost of being slower and
needing a one-time model download. Used by vision/handwriting.py as its
preferred engine, and available standalone here for anyone who wants
Hindi (or mixed Hindi/English) text read off the screen or an image.

    pip install easyocr   # optional, ~/.EasyOCR model download on first use

Same lazy-fetch approach as vision/object_detection/yolo_detector.py's
weights: EasyOCR downloads and caches its own model files on first run,
nothing is bundled here.
"""

from typing import Dict, Optional, Sequence

try:
    import easyocr
    import numpy as np

    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from vision.screen.capture import ScreenCapture

# EasyOCR language codes. "hi" = Hindi (Devanagari script). EasyOCR only
# allows combining Latin-based languages with at most one non-Latin
# script per reader, so "en"+"hi" together is the practical default for
# a Hinglish setup - mixing hi with other non-Latin scripts will fail.
DEFAULT_LANGUAGES = ("en", "hi")


class EasyOCROCR:
    """Extract text from the screen or an image file via EasyOCR,
    including Hindi/Devanagari script."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._readers: Dict[tuple, "easyocr.Reader"] = {}

    def _get_reader(self, languages: Sequence[str]):
        key = tuple(languages)
        if key not in self._readers:
            # gpu=False keeps this working on machines without CUDA; set
            # to True yourself if you have a GPU and want faster reads.
            self._readers[key] = easyocr.Reader(list(key), gpu=False)
        return self._readers[key]

    def read_screen(self, region: Optional[tuple] = None, languages: Sequence[str] = DEFAULT_LANGUAGES) -> Dict:
        """OCR the current screen (or a region of it)."""
        if not HAS_EASYOCR:
            return {"error": "easyocr not installed - run: pip install easyocr"}
        image = self._screen.capture(region=region)
        if isinstance(image, dict):
            return image
        return self._run_ocr(image, languages)

    def read_image(self, file_path: str, languages: Sequence[str] = DEFAULT_LANGUAGES) -> Dict:
        """OCR an existing image file."""
        if not HAS_EASYOCR:
            return {"error": "easyocr not installed - run: pip install easyocr"}
        if not HAS_PIL:
            return {"error": "Pillow not installed - run: pip install Pillow"}
        try:
            image = Image.open(file_path)
        except Exception as e:
            return {"error": str(e)}
        return self._run_ocr(image, languages)

    def _run_ocr(self, image, languages: Sequence[str]) -> Dict:
        try:
            reader = self._get_reader(languages)
            results = reader.readtext(np.array(image.convert("RGB")))
            words = [
                {"text": text, "confidence": round(float(conf), 3), "box": [[int(px), int(py)] for px, py in box]}
                for box, text, conf in results
            ]
            full_text = " ".join(w["text"] for w in words)
            return {
                "engine": "easyocr",
                "languages": list(languages),
                "text": full_text,
                "words": words,
                "word_count": len(words),
            }
        except Exception as e:
            return {"error": f"EasyOCR failed: {e}"}


_instance: "EasyOCROCR" = None


def get_easyocr() -> EasyOCROCR:
    global _instance
    if _instance is None:
        _instance = EasyOCROCR()
    return _instance
