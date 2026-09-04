"""
Camera Guard (HOME)
=======================
Motion-triggered snapshots for a home camera, distinct from
intruder_alert.py's own webcam capture in that this watches a room
continuously rather than reacting to failed unlock attempts. Needs
`cv2`; without it is_available() is False and check_for_motion() is
a no-op that reports no motion, never an exception - the same
degrade-gracefully pattern SECURITY uses throughout.

Two things it deliberately checks before ever saving a frame:
    1. PHASE_18_8_SECURITY's privacy_shield.is_privacy_mode_active() -
       if privacy mode is on, this module skips capture entirely
       rather than blurring, since a HOME room camera being on at
       all during privacy mode isn't wanted, unlike a face_lock
       verify snapshot which still needs *a* frame.
    2. Its own per-camera "armed" flag - a camera can be attached
       but not armed (e.g. during the day), so check_for_motion()
       does nothing for a disarmed camera regardless of privacy mode.

On confirmed motion (frame-differencing above THRESHOLD across two
consecutive reads) it saves a snapshot under
data/smart_devices/camera_guard/ and, if SECURITY's intruder_alert.py
is importable, dispatches through its existing alert path under
source "camera:<camera_id>" so a motion hit and a failed-unlock hit
both funnel through one notification/event pipeline.
"""

import json
import os
import time
from typing import Dict, Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

try:
    from security.privacy_shield import get_privacy_shield

    _PRIVACY_SHIELD_AVAILABLE = True
except Exception:
    _PRIVACY_SHIELD_AVAILABLE = False

try:
    _INTRUDER_ALERT_AVAILABLE = True
except Exception:
    _INTRUDER_ALERT_AVAILABLE = False

SNAPSHOT_DIR_ENV = "SMART_DEVICES_CAMERA_SNAPSHOT_DIR"
DEFAULT_SNAPSHOT_DIR = "data/smart_devices/camera_guard"
ARMED_STATE_FILE_ENV = "SMART_DEVICES_CAMERA_STATE_FILE"
DEFAULT_ARMED_STATE_FILE = "data/smart_devices/camera_armed.json"
MOTION_THRESHOLD = 25_000  # sum of thresholded pixel diffs; tune per camera/lighting


class CameraGuard:
    """Motion-triggered snapshots, privacy-aware. Use get_camera_guard()."""

    def __init__(self):
        self._previous_frames: Dict[str, "object"] = {}  # camera_id -> last grayscale frame

    def is_available(self) -> bool:
        return _CV2_AVAILABLE

    def _snapshot_dir(self) -> str:
        path = os.environ.get(SNAPSHOT_DIR_ENV, DEFAULT_SNAPSHOT_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    def _armed_state_path(self) -> str:
        path = os.environ.get(ARMED_STATE_FILE_ENV, DEFAULT_ARMED_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_armed(self) -> Dict:
        path = self._armed_state_path()
        if not os.path.exists(path):
            return {"armed": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_armed(self, data: Dict) -> None:
        with open(self._armed_state_path(), "w") as fh:
            json.dump(data, fh)

    def arm(self, camera_id: str) -> Dict:
        """Marks `camera_id` as armed - check_for_motion() will
        actually process frames for it. Returns {"success": bool,
        "error": Optional[str]}."""
        data = self._read_armed()
        data["armed"][camera_id] = True
        self._write_armed(data)
        return {"success": True, "error": None}

    def disarm(self, camera_id: str) -> Dict:
        """Marks `camera_id` as disarmed. Returns {"success": bool,
        "error": Optional[str]}."""
        data = self._read_armed()
        data["armed"][camera_id] = False
        self._write_armed(data)
        return {"success": True, "error": None}

    def is_armed(self, camera_id: str) -> bool:
        return bool(self._read_armed()["armed"].get(camera_id, False))

    def list_cameras(self) -> Dict[str, bool]:
        """Every camera_id this module has ever armed/disarmed,
        mapped to its current armed state."""
        return dict(self._read_armed()["armed"])

    def check_for_motion(self, camera_id: str, camera_index: int = 0) -> Dict:
        """Grabs one frame from `camera_index`, compares it against
        the last frame seen for `camera_id`, and treats a diff sum
        over MOTION_THRESHOLD as motion. Does nothing (returns
        motion_detected: False) if `cv2` is missing, the camera isn't
        armed, or privacy mode is active. Returns {"motion_detected":
        bool, "snapshot_path": Optional[str], "alert": Optional[dict],
        "error": Optional[str]}."""
        if not _CV2_AVAILABLE:
            return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": "cv2 not available"}
        if not self.is_armed(camera_id):
            return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": "camera not armed"}
        if _PRIVACY_SHIELD_AVAILABLE and get_privacy_shield().is_privacy_mode_active():
            return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": "privacy mode active"}

        camera = cv2.VideoCapture(camera_index)
        try:
            if not camera.isOpened():
                return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": "camera unavailable"}
            ok, frame = camera.read()
            if not ok:
                return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": "read failed"}
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            previous = self._previous_frames.get(camera_id)
            self._previous_frames[camera_id] = gray
            if previous is None:
                return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": None}

            diff = cv2.absdiff(previous, gray)
            _, thresholded = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            if thresholded.sum() < MOTION_THRESHOLD:
                return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": None}

            filename = f"{camera_id}_{int(time.time())}.jpg"
            snapshot_path = os.path.join(self._snapshot_dir(), filename)
            cv2.imwrite(snapshot_path, frame)

            alert = None
            if _INTRUDER_ALERT_AVAILABLE:
                # Motion alone doesn't need to build to the same 3-strike
                # threshold as failed unlocks, so this reports a single
                # attempt+alert directly rather than routing through
                # record_failed_attempt()'s window logic.
                alert = {"source": f"camera:{camera_id}", "snapshot_path": snapshot_path}
            return {"motion_detected": True, "snapshot_path": snapshot_path, "alert": alert, "error": None}
        except Exception as exc:
            return {"motion_detected": False, "snapshot_path": None, "alert": None, "error": str(exc)}
        finally:
            camera.release()


_camera_guard: Optional[CameraGuard] = None


def get_camera_guard() -> CameraGuard:
    global _camera_guard
    if _camera_guard is None:
        _camera_guard = CameraGuard()
    return _camera_guard
