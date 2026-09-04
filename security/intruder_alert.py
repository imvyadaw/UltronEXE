"""
Intruder Alert (SECURITY)
============================
The consequence side of face_lock.py/voice_lock.py: it doesn't do any
authentication itself, it just counts what those two report. A
caller (a wake-word handler, a vault unlock prompt, a future lock-
screen UI) calls record_failed_attempt() every time a verify() from
either lock comes back unsuccessful, and record_success() when one
succeeds. Three or more failures for the same `source` within
FAILURE_WINDOW_SECONDS trips an alert: a webcam snapshot (if `cv2` is
available) plus, if this build's notification hub
(ui/notifications.py, per the Phase 13 unified toast system) is
importable, a toast pushed straight to it. Neither is required - with
no OpenCV and no notification hub this module still tracks attempts
and returns the same alert dict, just with "snapshot_path": None.

Deliberately does not import face_lock.py or voice_lock.py itself -
this stays a plain attempt counter+alert dispatcher, so any future
auth factor (a PIN pad, an NFC tag) can drive it too without this
file needing to know about it.
"""

import os
import time
from typing import Dict, List, Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

try:
    from ui.notifications import get_notification_hub

    _NOTIFICATIONS_AVAILABLE = True
except Exception:
    _NOTIFICATIONS_AVAILABLE = False

try:
    from core.events import get_event_bus

    _EVENT_BUS_AVAILABLE = True
except Exception:
    _EVENT_BUS_AVAILABLE = False

SNAPSHOT_DIR_ENV = "SECURITY_ALERT_SNAPSHOT_DIR"
DEFAULT_SNAPSHOT_DIR = "data/security/alerts"
FAILURE_THRESHOLD = 3
FAILURE_WINDOW_SECONDS = 120
CAMERA_INDEX = 0


class IntruderAlert:
    """Failed-attempt tracking and alert dispatch. Use get_intruder_alert()."""

    def __init__(self):
        self._failures: Dict[str, List[float]] = {}

    def _snapshot_dir(self) -> str:
        path = os.environ.get(SNAPSHOT_DIR_ENV, DEFAULT_SNAPSHOT_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    def _capture_snapshot(self) -> Optional[str]:
        if not _CV2_AVAILABLE:
            return None
        camera = cv2.VideoCapture(CAMERA_INDEX)
        try:
            if not camera.isOpened():
                return None
            ok, frame = camera.read()
            if not ok:
                return None
            filename = f"intruder_{int(time.time())}.jpg"
            path = os.path.join(self._snapshot_dir(), filename)
            cv2.imwrite(path, frame)
            return path
        except Exception:
            return None
        finally:
            camera.release()

    def _dispatch(self, source: str, attempt_count: int, snapshot_path: Optional[str]) -> None:
        message = f"{attempt_count} failed unlock attempts ({source})"
        if _NOTIFICATIONS_AVAILABLE:
            try:
                get_notification_hub().notify(
                    title="Security alert",
                    message=message,
                    level="critical",
                    image_path=snapshot_path,
                )
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("security.intruder_alert._dispatch")
        if _EVENT_BUS_AVAILABLE:
            try:
                get_event_bus().publish(
                    "security.intruder_alert",
                    {
                        "source": source,
                        "attempt_count": attempt_count,
                        "snapshot_path": snapshot_path,
                        "timestamp": time.time(),
                    },
                )
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("security.intruder_alert._dispatch")

    def record_failed_attempt(self, source: str) -> Dict:
        """Logs a failed unlock attempt for `source` (e.g. "face_lock",
        "voice_lock", "vault"). Once FAILURE_THRESHOLD attempts land
        within FAILURE_WINDOW_SECONDS, this takes a snapshot (if
        possible) and dispatches an alert. Returns
        {"alert_triggered": bool, "attempt_count": int,
        "snapshot_path": Optional[str]}."""
        now = time.time()
        window_start = now - FAILURE_WINDOW_SECONDS
        attempts = [t for t in self._failures.get(source, []) if t >= window_start]
        attempts.append(now)
        self._failures[source] = attempts

        if len(attempts) < FAILURE_THRESHOLD:
            return {"alert_triggered": False, "attempt_count": len(attempts), "snapshot_path": None}

        snapshot_path = self._capture_snapshot()
        self._dispatch(source, len(attempts), snapshot_path)
        self._failures[source] = []  # reset window after alerting, don't re-fire every attempt
        return {"alert_triggered": True, "attempt_count": len(attempts), "snapshot_path": snapshot_path}

    def record_success(self, source: str) -> None:
        """Clears `source`'s failure history after a successful
        unlock, so a normal correct attempt after a couple of typos
        doesn't linger toward the threshold."""
        self._failures[source] = []

    def failure_count(self, source: str) -> int:
        """Attempts for `source` still inside the current window."""
        window_start = time.time() - FAILURE_WINDOW_SECONDS
        return len([t for t in self._failures.get(source, []) if t >= window_start])


_intruder_alert: Optional[IntruderAlert] = None


def get_intruder_alert() -> IntruderAlert:
    global _intruder_alert
    if _intruder_alert is None:
        _intruder_alert = IntruderAlert()
    return _intruder_alert
