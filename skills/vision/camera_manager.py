"""
skills/vision/camera_manager.py
=================================
Skill-layer wrapper around eyes/live_camera.py's LiveCamera. No camera-
opening logic lives here - get_live_camera() stays the one place in the
project that calls cv2.VideoCapture. This module only adds what a
higher-level skill actually needs on top of that: a warmed-up frame and
a JPEG snapshot saved to disk (models/vision/loader.py's
describe_image() takes a file path, not raw pixels).
"""

import os
import time
import uuid
from typing import Optional

from config import CAMERA_SNAPSHOT_DIR, CAMERA_WARMUP_FRAMES
from eyes.live_camera import get_live_camera

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False


class CameraManager:
    """Skill-facing camera access - built on top of the single shared
    LiveCamera instance, never a device handle of its own."""

    def __init__(self):
        self._camera = get_live_camera()

    def is_available(self) -> bool:
        """True only if opencv is installed AND the shared camera can
        actually be started - mirrors LiveCamera.is_available()'s two
        independent failure modes."""
        if not _CV2_AVAILABLE:
            return False
        return self._camera.start()

    def get_frame(self):
        """Start the camera if needed, discard CAMERA_WARMUP_FRAMES
        frames so auto-exposure/white-balance settle, and return the
        next frame (a cv2/numpy array) or None."""
        if not self._camera.start():
            return None
        frame = None
        for _ in range(max(1, CAMERA_WARMUP_FRAMES)):
            frame = self._camera.get_frame()
        return frame

    def capture_snapshot(self, save_path: Optional[str] = None) -> Optional[str]:
        """Capture a frame and save it as a JPEG. Returns the file path,
        or None if the camera/opencv isn't available. If save_path isn't
        given, writes a timestamped file under CAMERA_SNAPSHOT_DIR."""
        if not _CV2_AVAILABLE:
            return None
        frame = self.get_frame()
        if frame is None:
            return None

        if save_path is None:
            os.makedirs(CAMERA_SNAPSHOT_DIR, exist_ok=True)
            filename = f"snapshot_{int(time.time())}_{uuid.uuid4().hex[:8]}.jpg"
            save_path = os.path.join(CAMERA_SNAPSHOT_DIR, filename)
        else:
            parent = os.path.dirname(save_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        try:
            ok = cv2.imwrite(save_path, frame)
        except Exception:
            return None
        return save_path if ok else None

    def stop(self) -> None:
        """Release the shared camera device. Only call this when the
        assistant is done looking (e.g. session teardown) - other
        callers (face lock, intruder alert, etc.) share the same
        LiveCamera instance."""
        self._camera.stop()


_camera_manager: Optional[CameraManager] = None


def get_camera_manager() -> CameraManager:
    """Process-wide CameraManager singleton, matching this codebase's
    get_x() convention."""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager()
    return _camera_manager
