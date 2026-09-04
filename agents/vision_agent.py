"""
Vision agent
============
Wraps vision/screen, vision/ocr, vision/face, vision/object_detection,
and vision/ui_detection into one entry point - the way agents/assistant_agent.py
wraps core/brain.py, and windows/__init__.py's SystemTools wraps windows/.
vision/gestures/ isn't included here since it's about a live camera/video
stream rather than a single screen/image snapshot.

Phase 10 additions: named-person face recognition (on top of plain face
detection), YOLO-based object detection (80 COCO classes, up from the
old 20-class MobileNet-SSD), icon-only UI element detection alongside
the existing text-based one, and start/stop screen recording.
"""

from typing import Dict, Optional

from vision.screen.capture import ScreenCapture
from vision.screen.recorder import ScreenRecorder
from vision.ocr.tesseract_ocr import OCR
from vision.face.detection import FaceDetector
from vision.face.recognition import FaceRecognition
from vision.object_detection.yolo_detector import ObjectDetector
from vision.object_detection.ui_detector import UIObjectDetector
from vision.ui_detection.element_locator import UIDetector
from agents.base_agent import BaseAgent


class VisionAgent(BaseAgent):
    """One-stop "what's on screen" agent: text, faces, objects, UI regions."""

    capabilities = ["vision", "ocr", "screen", "image", "faces", "objects", "recording"]

    def __init__(self):
        super().__init__("vision", "Screen capture + OCR/face/object/UI detection")
        self._screen = ScreenCapture()
        self._recorder = ScreenRecorder()
        self._ocr = OCR()
        self._faces = FaceDetector()
        self._face_id = FaceRecognition()
        self._objects = ObjectDetector()
        self._icons = UIObjectDetector()
        self._ui = UIDetector()

    def see(self, region: Optional[tuple] = None) -> Dict:
        """Grab the current screen once and run every vision tool against
        that single capture, so results are consistent with each other."""
        image = self._screen.capture(region=region)
        if isinstance(image, dict):
            return image

        return {
            "text": self._ocr._run_ocr(image),
            "faces": self._faces.detect_faces(image),
            "objects": self._objects.detect(image),
            "ui_regions": self._ui.find_text_regions(image),
            "icon_buttons": self._icons.find_icon_buttons(image),
        }

    def read_text(self) -> Dict:
        """Just OCR the current screen."""
        return self._ocr.read_screen()

    def detect_faces(self) -> Dict:
        """Just face detection (bounding boxes only) on the current screen."""
        return self._faces.detect_faces()

    def enroll_face(self, name: str, file_path: Optional[str] = None) -> Dict:
        """Enroll a reference photo for `name` so recognize_faces() can
        identify them later. Uses the current screen if no file is given."""
        return self._face_id.enroll(name, file_path=file_path)

    def recognize_faces(self) -> Dict:
        """Identify faces on the current screen against enrolled people."""
        return self._face_id.recognize()

    def detect_objects(self) -> Dict:
        """Just object detection (YOLOv8, 80 COCO classes) on the current screen."""
        return self._objects.detect()

    def find_icon_buttons(self) -> Dict:
        """Locate unlabeled icon/button-shaped UI elements on the current screen."""
        return self._icons.find_icon_buttons()

    def start_recording(self, filepath: str, duration_seconds: Optional[float] = None) -> Dict:
        """Start recording the screen to an .mp4 file."""
        return self._recorder.start(filepath, duration_seconds=duration_seconds)

    def stop_recording(self) -> Dict:
        """Stop an in-progress screen recording."""
        return self._recorder.stop()
