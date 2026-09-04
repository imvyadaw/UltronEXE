"""
ScreenCapture
=============
Grabs a screenshot as an in-memory PIL Image (unlike
windows/display/display.py's take_screenshot(), which saves straight to
disk) so vision/ocr/ocr.py and any future object/UI-detection module can
run analysis on it without a round-trip through the filesystem.
"""

from pathlib import Path
from typing import Dict, Optional

try:
    from PIL import ImageGrab

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ScreenCapture:
    """Grab the screen (or a region of it) as a PIL Image, with an
    optional save-to-disk convenience for callers that want a file too."""

    def capture(self, region: Optional[tuple] = None):
        """Grab the current screen as a PIL Image.

        region: optional (left, top, right, bottom) box in pixels to grab
        instead of the full screen.
        Returns the PIL Image on success, or a dict with an 'error' key
        on failure (checked with isinstance(result, dict) by callers).
        """
        if not HAS_PIL:
            return {"error": "Pillow not installed - run: pip install Pillow"}
        try:
            return ImageGrab.grab(bbox=region)
        except Exception as e:
            return {"error": str(e)}

    def capture_to_file(self, filepath: str, region: Optional[tuple] = None) -> Dict:
        """Grab the screen and save it straight to `filepath`."""
        image = self.capture(region=region)
        if isinstance(image, dict):
            return image
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            image.save(filepath)
            return {"success": True, "saved_to": filepath, "size": image.size}
        except Exception as e:
            return {"error": str(e)}
