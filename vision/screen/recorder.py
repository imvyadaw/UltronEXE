"""
Screen recorder
================
Records the screen (or a region of it) to an .mp4 file, by repeatedly
grabbing frames with vision/screen/capture.py's ScreenCapture and
writing them out with OpenCV's VideoWriter. This is a synchronous,
poll-in-a-thread recorder (not a true screen-capture-API hook), so it's
CPU-bound by how fast ImageGrab + a frame-encode can run - fine for
short clips/demos/tutorials at a modest fps (10-15), not meant to
replace a dedicated capture tool like OBS for high-fps gameplay
recording.
"""

import threading
import time
from pathlib import Path
from typing import Dict, Optional

try:
    import cv2
    import numpy as np

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from vision.screen.capture import ScreenCapture

DEFAULT_FPS = 10
FOURCC = "mp4v"


class ScreenRecorder:
    """Start/stop screen recording to an .mp4 file. Not thread-safe
    across overlapping recordings - one recording at a time per instance."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._recording = False
        self._output_path: Optional[str] = None
        self._error: Optional[str] = None

    def start(
        self,
        filepath: str,
        region: Optional[tuple] = None,
        fps: int = DEFAULT_FPS,
        duration_seconds: Optional[float] = None,
    ) -> Dict:
        """Start recording in a background thread. If duration_seconds is
        given, recording stops automatically after that long; otherwise
        call stop() to end it."""
        if not HAS_CV2:
            return {"error": "opencv-python not installed - run: pip install opencv-python-headless"}
        if self._recording:
            return {"error": "A recording is already in progress - call stop() first"}

        first_frame = self._screen.capture(region=region)
        if isinstance(first_frame, dict):
            return first_frame

        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            width, height = first_frame.size
            fourcc = cv2.VideoWriter_fourcc(*FOURCC)
            writer = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
            if not writer.isOpened():
                return {
                    "error": f"Could not open VideoWriter for '{filepath}' - the mp4v codec "
                    "may not be available in your OpenCV build"
                }
        except Exception as e:
            return {"error": str(e)}

        self._output_path = filepath
        self._error = None
        self._stop_event.clear()
        self._recording = True
        self._thread = threading.Thread(
            target=self._record_loop,
            args=(writer, region, fps, duration_seconds),
            daemon=True,
        )
        self._thread.start()
        return {"success": True, "recording_to": filepath, "fps": fps}

    def _record_loop(self, writer, region, fps: int, duration_seconds: Optional[float]) -> None:
        interval = 1.0 / fps
        start_time = time.monotonic()
        try:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()
                if duration_seconds is not None and (loop_start - start_time) >= duration_seconds:
                    break

                frame = self._screen.capture(region=region)
                if isinstance(frame, dict):
                    self._error = frame.get("error", "capture failed mid-recording")
                    break

                bgr = cv2.cvtColor(np.array(frame.convert("RGB")), cv2.COLOR_RGB2BGR)
                writer.write(bgr)

                elapsed = time.monotonic() - loop_start
                sleep_for = interval - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            writer.release()
            self._recording = False

    def stop(self) -> Dict:
        """Stop an in-progress recording."""
        if not self._recording:
            return {"error": "No recording in progress"}
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._error:
            return {"error": self._error}
        return {"success": True, "saved_to": self._output_path}

    def status(self) -> Dict:
        return {"recording": self._recording, "output_path": self._output_path}


_instance: "ScreenRecorder" = None


def get_screen_recorder() -> ScreenRecorder:
    global _instance
    if _instance is None:
        _instance = ScreenRecorder()
    return _instance
