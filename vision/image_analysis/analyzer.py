"""
Image analysis
===============
Basic quantitative analysis of an image (or the current screen) - size,
average brightness, dominant colors, edge density. Pure PIL/numpy, no
GPU or extra model download needed, unlike object/face detection above.
"""

from typing import Dict

try:
    from PIL import ImageFilter
    import numpy as np

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

from vision.screen.capture import ScreenCapture


class ImageAnalyzer:
    """Basic pixel-level stats about an image: brightness, dominant
    colors, edge density, resolution."""

    def __init__(self):
        self._screen = ScreenCapture()

    def analyze(self, image=None, top_colors: int = 5) -> Dict:
        """Analyze a PIL Image, or the current screen if none given."""
        if not HAS_DEPS:
            return {"error": "Pillow/numpy not installed - run: pip install Pillow numpy"}

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        try:
            rgb = image.convert("RGB")
            arr = np.array(rgb)

            brightness = float(arr.mean())

            small = rgb.resize((100, 100))
            counts = small.getcolors(maxcolors=10000) or []
            counts.sort(key=lambda c: c[0], reverse=True)
            dominant = [
                {"rgb": list(color), "hex": "#%02x%02x%02x" % color, "frequency": count}
                for count, color in counts[:top_colors]
            ]

            edges = rgb.convert("L").filter(ImageFilter.FIND_EDGES)
            edge_arr = np.array(edges)
            edge_density = float((edge_arr > 30).mean())

            return {
                "width": rgb.width,
                "height": rgb.height,
                "average_brightness": round(brightness, 1),
                "is_mostly_dark": brightness < 85,
                "dominant_colors": dominant,
                "edge_density": round(edge_density, 4),
            }
        except Exception as e:
            return {"error": str(e)}
