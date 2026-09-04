"""
Tesseract OCR
=============
Text extraction from a screenshot or image file, via pytesseract
(wraps the system Tesseract binary). Fast and fully offline, but
weakest of the two OCR engines on handwriting, stylized fonts, or
Indian-language scripts - see vision/ocr/easyocr_ocr.py for those
cases. Builds on vision/screen/capture.py for the "read what's on my
screen" case.

Requires the Tesseract binary installed separately from the Python
package (pip install pytesseract only installs the Python wrapper):
  Windows: https://github.com/UB-Mannheim/tesseract/wiki
  Linux:   apt install tesseract-ocr
  macOS:   brew install tesseract
"""

from typing import Dict, Optional

try:
    import pytesseract
    from PIL import Image

    HAS_OCR = True
except ImportError:
    HAS_OCR = False

from config import TESSERACT_CMD
from vision.screen.capture import ScreenCapture

if HAS_OCR and TESSERACT_CMD:
    # Points pytesseract straight at the binary when it isn't on PATH -
    # the common case on Windows, where the installer often skips the
    # PATH step. See config.py for TESSERACT_CMD.
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


class TesseractOCR:
    """Extract text from the screen or an image file via Tesseract."""

    def __init__(self):
        self._screen = ScreenCapture()

    def read_screen(self, region: Optional[tuple] = None, lang: str = "eng") -> Dict:
        """OCR the current screen (or a region of it)."""
        if not HAS_OCR:
            return {
                "error": "pytesseract not installed - run: pip install pytesseract "
                "(and install the Tesseract binary itself - see this module's docstring)"
            }
        image = self._screen.capture(region=region)
        if isinstance(image, dict):
            return image
        return self._run_ocr(image, lang=lang)

    def read_image(self, file_path: str, lang: str = "eng") -> Dict:
        """OCR an existing image file (screenshot, photo, scanned doc, etc.)."""
        if not HAS_OCR:
            return {
                "error": "pytesseract not installed - run: pip install pytesseract "
                "(and install the Tesseract binary itself - see this module's docstring)"
            }
        try:
            image = Image.open(file_path)
        except Exception as e:
            return {"error": str(e)}
        return self._run_ocr(image, lang=lang)

    def _run_ocr(self, image, lang: str = "eng") -> Dict:
        try:
            text = pytesseract.image_to_string(image, lang=lang)
            return {"engine": "tesseract", "text": text.strip(), "char_count": len(text.strip())}
        except pytesseract.TesseractNotFoundError:
            return {
                "error": "Tesseract binary not found on PATH - install it separately from "
                "pytesseract (see this module's docstring for the per-OS install command)"
            }
        except pytesseract.TesseractError as e:
            if lang != "eng":
                return {
                    "error": f"Tesseract error with lang='{lang}' - the matching .traineddata "
                    f"(e.g. hin.traineddata for Hindi) may not be installed for your "
                    f"Tesseract binary. Original error: {e}"
                }
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}


# Backwards-compatible alias - the class used to be called OCR before it
# moved into ocr/tesseract_ocr.py alongside ocr/easyocr_ocr.py.
OCR = TesseractOCR
