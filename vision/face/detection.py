"""
Face detection
==============
Face *detection* (where are the faces?) via OpenCV's bundled Haar Cascade
classifier - lightweight, ships with opencv-python, no GPU or extra model
download needed. This is NOT face *recognition* (whose face is it?) -
identifying a specific person is vision/face/recognition.py, a separate
module built on top of this one's bounding boxes.
"""

from typing import Dict

try:
    import cv2
    import numpy as np

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from vision.screen.capture import ScreenCapture


class FaceDetector:
    """Face detection (bounding boxes), not identification."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._cascade = None

    def _get_cascade(self):
        if self._cascade is None:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._cascade = cv2.CascadeClassifier(path)
        return self._cascade

    def detect_faces(self, image=None) -> Dict:
        """Detect faces in a PIL Image, or the current screen if none given.
        Returns bounding boxes in (x, y, width, height) pixel coordinates."""
        if not HAS_CV2:
            return {"error": "opencv-python not installed - run: pip install opencv-python-headless"}

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        try:
            frame = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            cascade = self._get_cascade()
            boxes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            faces = [{"x": int(x), "y": int(y), "width": int(w), "height": int(h)} for (x, y, w, h) in boxes]
            return {"face_count": len(faces), "faces": faces}
        except Exception as e:
            return {"error": str(e)}


# Backwards-compatible alias for callers written against the old
# vision/face/face.py module.
FaceRecognizer = FaceDetector
