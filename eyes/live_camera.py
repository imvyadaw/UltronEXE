"""
Live Camera
===========
The one module in EYES/ allowed to open a device. Every other module
in this package takes a frame as a plain argument instead of reaching
for a camera itself - the same separation MEMORY/face_memory.py drew
between "storage and naming" (its job) and "pixels" (vision/'s job),
just one level lower: here it's "opening the device" vs "doing
anything with what comes out of it".

cv2.VideoCapture is the only backend wired up. If opencv-python isn't
installed, or index 0 has no camera attached (headless dev box, no
webcam yet), start() returns False and get_frame() returns None -
never an exception. That mirrors PLACE_MEMORY.py's stance on a
location provider not being wired up yet: a hardware dependency not
being available is an expected, not exceptional, state for this
project pre-deployment.
"""

import time
from typing import Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False


class LiveCamera:
    """Thin wrapper over a single camera device. Use get_live_camera()."""

    def __init__(self, device_index: int = 0):
        self._device_index = device_index
        self._cap = None
        self._last_frame = None
        self._last_frame_at = 0.0

    def is_available(self) -> bool:
        """True only if opencv is installed AND the device actually
        opened - two independent failure modes, both degrade the
        same way for callers."""
        return _CV2_AVAILABLE and self._cap is not None and self._cap.isOpened()

    def start(self) -> bool:
        if not _CV2_AVAILABLE:
            return False
        if self._cap is not None and self._cap.isOpened():
            return True
        try:
            self._cap = cv2.VideoCapture(self._device_index)
            return self._cap.isOpened()
        except Exception:
            self._cap = None
            return False

    def stop(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("eyes.live_camera.stop")
        self._cap = None

    def get_frame(self):
        """Returns the newest frame (a cv2/numpy array) or None. Also
        caches it as last_frame() so a caller that just wants
        "whatever EYES most recently saw" (e.g. DISPLAY/orb.py) doesn't
        need to hold its own camera handle."""
        if not self.is_available():
            return None
        try:
            ok, frame = self._cap.read()
        except Exception:
            return None
        if not ok:
            return None
        self._last_frame = frame
        self._last_frame_at = time.time()
        return frame

    def last_frame(self, max_age_seconds: Optional[float] = None):
        """Returns the most recently captured frame without touching
        the device again. If max_age_seconds is given and the cached
        frame is older than that, returns None instead of stale
        pixels."""
        if self._last_frame is None:
            return None
        if max_age_seconds is not None and (time.time() - self._last_frame_at) > max_age_seconds:
            return None
        return self._last_frame


_live_camera: Optional[LiveCamera] = None


def get_live_camera() -> LiveCamera:
    global _live_camera
    if _live_camera is None:
        _live_camera = LiveCamera()
    return _live_camera
