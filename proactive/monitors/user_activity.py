"""
User activity monitor
======================
"What is the user doing right now" - active window title and idle time
(seconds since the last keyboard/mouse input). Used by:
  - triggers/event_driven.py, to notice an app just changed focus
  - scenarios/work_monitor.py, to suggest a break after long idle-free
    stretches, or to stay quiet while the user is clearly heads-down
  - triggers/time_based.py, so a scheduled briefing can be held back a
    few minutes if the user is mid-idle (e.g. stepped away) rather than
    firing into an empty room

Windows-first (this project's primary target platform - see
requirements.txt's pygetwindow/pywin32), with soft fallbacks everywhere:
missing optional packages or an unsupported OS mean "unknown", never a
crash.
"""

import sys
import time
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.proactive.user_activity")

try:
    import pygetwindow as gw

    HAS_PYGETWINDOW = True
except ImportError:
    HAS_PYGETWINDOW = False


def _idle_seconds_windows() -> Optional[float]:
    """GetLastInputInfo via ctypes - no extra dependency beyond stdlib +
    the pywin32/ctypes that's already available on Windows."""
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        millis_idle = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        return millis_idle / 1000.0
    except Exception as e:
        logger.debug(f"Idle-time read unavailable: {e}")
        return None


class UserActivityMonitor:
    """Active window + idle time, best-effort across platforms."""

    def __init__(self):
        self._last_active_window: Optional[str] = None

    def active_window_title(self) -> Optional[str]:
        if not HAS_PYGETWINDOW:
            return None
        try:
            win = gw.getActiveWindow()
            return win.title if win and win.title else None
        except Exception as e:
            logger.debug(f"Active window read unavailable: {e}")
            return None

    def idle_seconds(self) -> Optional[float]:
        if sys.platform == "win32":
            return _idle_seconds_windows()
        # No cross-platform idle-time story without extra native
        # dependencies (Xss on Linux, IOHIDSystem on macOS) - honest
        # "unknown" rather than pretending 0.
        return None

    def snapshot(self) -> Dict:
        return {
            "timestamp": time.time(),
            "active_window": self.active_window_title(),
            "idle_seconds": self.idle_seconds(),
        }

    def has_window_changed(self) -> Optional[str]:
        """Returns the new window title if the active window changed since
        the last call, else None. Stateful - meant to be polled repeatedly
        by triggers/event_driven.py, not called from multiple places."""
        current = self.active_window_title()
        if current and current != self._last_active_window:
            previous = self._last_active_window
            self._last_active_window = current
            if previous is not None:  # skip the very first reading
                return current
        elif current:
            self._last_active_window = current
        return None


_monitor: Optional[UserActivityMonitor] = None


def get_user_activity_monitor() -> UserActivityMonitor:
    global _monitor
    if _monitor is None:
        _monitor = UserActivityMonitor()
    return _monitor
