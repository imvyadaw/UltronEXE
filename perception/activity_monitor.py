"""
Activity Monitor (Phase 22 - Perception)
=========================================
proactive/monitors/user_activity.py already reads the active window
title and idle time, stateful enough to answer "did the window change
since I last asked" - this module doesn't duplicate that reading logic,
it wraps it with the Phase 21/22 plumbing that module deliberately
doesn't own: a normalized perception event on core.event_bus, and an
optional polling loop so nothing needs to call has_window_changed() in
its own while-loop.

Also folds in process-level activity (windows/process/manager.py's
top processes by resource use) as an optional heavier reading -
left out of the default snapshot() since it's noticeably more
expensive than a window-title read, available via
snapshot(include_processes=True) for callers that want it (e.g.
system_listener cross-checking a resource spike against what's active).
"""

import threading
import time
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.perception.activity_monitor")

DEFAULT_POLL_SECONDS = 5.0


class ActivityMonitor:
    def __init__(self):
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

    def snapshot(self, include_processes: bool = False) -> Dict:
        """One-off reading: active window + idle time, optionally top
        processes. Never raises - missing optional deps mean a None
        field, same convention as the underlying monitor."""
        from proactive.monitors.user_activity import get_user_activity_monitor

        base = get_user_activity_monitor().snapshot()

        data = {
            "active_window": base.get("active_window"),
            "idle_seconds": base.get("idle_seconds"),
            "is_idle": (base.get("idle_seconds") or 0) > 300,
            "top_processes": self._top_processes() if include_processes else None,
        }
        return self._emit(data)

    def _top_processes(self, limit: int = 5) -> Optional[list]:
        try:
            from windows.process.manager import ProcessManager

            result = ProcessManager().list_processes(sort_by="cpu", limit=limit)
            return result.get("processes") if isinstance(result, dict) else None
        except Exception as exc:
            logger.debug(f"activity_monitor: process listing unavailable: {exc}")
            return None

    # -- change detection / polling -----------------------------------
    def check_for_change(self) -> Optional[Dict]:
        """Non-blocking: returns a perception event only if the active
        window changed since the last call, else None. Delegates the
        actual state-diffing to user_activity.has_window_changed()."""
        from proactive.monitors.user_activity import get_user_activity_monitor

        new_title = get_user_activity_monitor().has_window_changed()
        if not new_title:
            return None
        return self._emit({"active_window": new_title, "changed": True}, event_name="perception.activity_changed")

    def start_polling(self, interval_seconds: float = DEFAULT_POLL_SECONDS) -> None:
        """Background thread calling check_for_change() on an interval.
        Idempotent - calling this again while already running is a no-op."""
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_flag.clear()

        def _loop():
            while not self._stop_flag.is_set():
                try:
                    self.check_for_change()
                except Exception:
                    logger.exception("activity_monitor: poll iteration failed")
                self._stop_flag.wait(interval_seconds)

        self._poll_thread = threading.Thread(target=_loop, daemon=True, name="activity-monitor-poll")
        self._poll_thread.start()

    def stop_polling(self) -> None:
        self._stop_flag.set()

    # -- emit ----------------------------------------------------------
    def _emit(self, data: Dict, event_name: str = "perception.activity") -> Dict:
        event = {"modality": "activity", "timestamp": time.time(), "data": data, "source": "activity_monitor"}
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(event_name, **event)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.activity_monitor._emit")
        try:
            from core.unified_context import get_unified_context

            ctx = get_unified_context()
            if data.get("active_window"):
                ctx.conversation_context.set_active_app(data["active_window"])
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("perception.activity_monitor._emit")
        return event


_monitor: Optional[ActivityMonitor] = None


def get_activity_monitor() -> ActivityMonitor:
    global _monitor
    if _monitor is None:
        _monitor = ActivityMonitor()
    return _monitor
