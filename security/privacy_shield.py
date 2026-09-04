"""
Privacy Shield (SECURITY)
============================
A single project-wide flag - "privacy mode" - plus one image utility
to act on it. This module never touches the camera or mic itself and
never silences anything by force; it's a shared switch that other
modules are expected to check:

    is_privacy_mode_active()  - a wake-word listener, a webcam-based
                                  gesture phase, or intruder_alert.py's
                                  own snapshot capture can all call
                                  this first and skip themselves while
                                  it's True. Persisted to disk (not
                                  just in-memory) so it survives a
                                  restart - privacy mode turned on
                                  before leaving the house should
                                  still be on when Ultron relaunches.
    blur_frame()               - for the times a frame must still be
                                  captured (e.g. face_lock.py's own
                                  verify snapshot) but shouldn't be
                                  kept sharp - Gaussian-blurs a
                                  region or the whole frame in place.
                                  Needs `cv2`; without it this is a
                                  no-op that returns the frame
                                  unchanged, never an exception.

Enabling privacy mode does not retroactively touch anything already
captured (face_lock.py's stored encodings, intruder_alert.py's past
snapshots) - it only affects what happens after enable() is called.
"""

import json
import os
from typing import Dict, Optional

try:
    import cv2

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

STATE_FILE_ENV = "SECURITY_PRIVACY_STATE_FILE"
DEFAULT_STATE_FILE = "data/security/privacy_state.json"
DEFAULT_BLUR_KERNEL = (51, 51)


class PrivacyShield:
    """Persisted privacy-mode flag + frame blurring. Use get_privacy_shield()."""

    def __init__(self):
        self._active: Optional[bool] = None  # lazily loaded from disk

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _load(self) -> bool:
        if self._active is not None:
            return self._active
        path = self._state_path()
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    self._active = bool(json.load(fh).get("active", False))
            except Exception:
                self._active = False
        else:
            self._active = False
        return self._active

    def _save(self) -> None:
        try:
            with open(self._state_path(), "w") as fh:
                json.dump({"active": self._active}, fh)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("security.privacy_shield._save")

    def is_privacy_mode_active(self) -> bool:
        """Whether privacy mode is currently on. Loads from disk on
        first call in this process so a fresh launch respects
        whatever it was set to last."""
        return self._load()

    def enable(self, reason: Optional[str] = None) -> Dict:
        """Turns privacy mode on. `reason` is accepted for callers
        that want to log why (e.g. "leaving home") but isn't
        required or stored beyond this call. Returns
        {"success": bool, "error": Optional[str]}."""
        self._active = True
        self._save()
        return {"success": True, "error": None}

    def disable(self) -> Dict:
        """Turns privacy mode off. Returns
        {"success": bool, "error": Optional[str]}."""
        self._active = False
        self._save()
        return {"success": True, "error": None}

    def toggle(self) -> Dict:
        """Flips the current state. Returns
        {"success": bool, "active": bool, "error": Optional[str]}."""
        self._load()
        self._active = not self._active
        self._save()
        return {"success": True, "active": self._active, "error": None}

    def blur_frame(self, frame, region: Optional[tuple] = None):
        """Gaussian-blurs `frame` (a numpy BGR array, as from cv2) in
        place and returns it. `region` is an optional (x, y, w, h) box
        to blur just that area (e.g. a detected face) rather than the
        whole frame - leave it None to blur everything. Without `cv2`
        this returns `frame` completely unchanged; it never raises."""
        if not _CV2_AVAILABLE or frame is None:
            return frame
        try:
            if region is None:
                return cv2.GaussianBlur(frame, DEFAULT_BLUR_KERNEL, 0)
            x, y, w, h = region
            roi = frame[y : y + h, x : x + w]
            frame[y : y + h, x : x + w] = cv2.GaussianBlur(roi, DEFAULT_BLUR_KERNEL, 0)
            return frame
        except Exception:
            return frame


_privacy_shield: Optional[PrivacyShield] = None


def get_privacy_shield() -> PrivacyShield:
    global _privacy_shield
    if _privacy_shield is None:
        _privacy_shield = PrivacyShield()
    return _privacy_shield
