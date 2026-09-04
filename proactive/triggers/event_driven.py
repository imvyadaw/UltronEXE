"""
Event-driven triggers
======================
Discrete, one-off happenings rather than a threshold or a clock time:
"an app just got focus", "a watched file just changed". App-focus
detection is poll-based (proactive/monitors/user_activity.py's
has_window_changed(), called once per engine tick - see engine.py).
File-change detection is deliberately NOT built on top of
automation/triggers/file_watcher.py - that module's `watch()` fires a
named Ultron *tool call*, which doesn't fit what's needed here (a plain
Python callback that drops an event on a queue for check() to drain).
Instead this keeps its own minimal watcher: watchdog if the optional
package is installed (see requirements.txt), otherwise a simple mtime
polling thread - same fallback philosophy as file_watcher.py, just
scoped to this module's own queue-based use case instead of sharing
its (differently-shaped) implementation.

Only a small allow-list of "interesting" app names triggers an alert by
default (see INTERESTING_APPS) - most focus changes (switching between
two browser tabs, alt-tabbing to check the clock) are noise, not signal.
"""

import queue
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from proactive.monitors.user_activity import get_user_activity_monitor
from core.logger import get_logger

logger = get_logger("ultron.proactive.event_driven")

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# Substrings matched case-insensitively against the active window title.
# Deliberately small/conservative - extend via add_interesting_app()
# rather than alerting on every single focus change.
INTERESTING_APPS: Set[str] = {"zoom", "teams", "outlook", "visual studio code", "vscode"}


class EventDrivenTriggers:
    """App-focus (poll-based) + file-change (watchdog/polling via
    automation.triggers.file_watcher, drained from a queue) events."""

    def __init__(self):
        self._activity = get_user_activity_monitor()
        self._interesting_apps: Set[str] = set(INTERESTING_APPS)
        self._file_events: "queue.Queue[Dict]" = queue.Queue()
        self._lock = threading.Lock()

    def add_interesting_app(self, name_substring: str) -> None:
        with self._lock:
            self._interesting_apps.add(name_substring.lower())

    def _on_change(self, changed_path: str, event_type: str) -> None:
        self._file_events.put({"name": changed_path, "event_type": event_type})

    def watch_path(self, path: str, recursive: bool = False, poll_interval: float = 2.0) -> Dict:
        """Start watching a file/folder; matching changes are queued and
        surfaced as 'file_changed' events on the next check(). Uses
        watchdog if installed, else a background mtime-polling thread -
        never raises if the path or the optional dependency is missing."""
        target = Path(path)
        if not target.exists():
            return {"success": False, "error": f"Path does not exist: {path}"}

        if HAS_WATCHDOG:
            handler = self._make_watchdog_handler()
            observer = Observer()
            observer.schedule(handler, str(target), recursive=recursive)
            observer.daemon = True
            observer.start()
            return {"success": True, "backend": "watchdog", "path": str(target)}

        stop_flag = threading.Event()
        thread = threading.Thread(
            target=self._poll_loop, args=(target, recursive, poll_interval, stop_flag), daemon=True
        )
        thread.start()
        return {"success": True, "backend": "polling", "path": str(target)}

    def _make_watchdog_handler(self):
        outer = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory:
                    outer._on_change(event.src_path, "created")

            def on_modified(self, event):
                if not event.is_directory:
                    outer._on_change(event.src_path, "modified")

            def on_deleted(self, event):
                if not event.is_directory:
                    outer._on_change(event.src_path, "deleted")

        return _Handler()

    def _poll_loop(self, target: Path, recursive: bool, interval: float, stop_flag: threading.Event) -> None:
        """Fallback when watchdog isn't installed: snapshot file mtimes and
        diff on each tick. Fine for a handful of watched paths at a couple
        of seconds' resolution; not meant for large recursive trees."""

        def snapshot() -> Dict[str, float]:
            try:
                if target.is_file():
                    return {str(target): target.stat().st_mtime}
                pattern = "**/*" if recursive else "*"
                return {str(p): p.stat().st_mtime for p in target.glob(pattern) if p.is_file()}
            except Exception as e:
                logger.debug(f"File poll snapshot failed: {e}")
                return {}

        previous = snapshot()
        while not stop_flag.is_set():
            time.sleep(interval)
            current = snapshot()
            for name, mtime in current.items():
                if name not in previous:
                    self._on_change(name, "created")
                elif mtime != previous[name]:
                    self._on_change(name, "modified")
            for name in previous:
                if name not in current:
                    self._on_change(name, "deleted")
            previous = current

    def check(self) -> List[Dict]:
        """Returns events ready for tone_manager.get_phrase(): 'app_opened'
        when an interesting app takes focus, 'file_changed' for anything
        queued by a registered file watch."""
        events: List[Dict] = []

        new_window = self._activity.has_window_changed()
        if new_window:
            lowered = new_window.lower()
            with self._lock:
                interesting = self._interesting_apps
            if any(app in lowered for app in interesting):
                events.append({"category": "app_opened", "kwargs": {"name": new_window}})

        while True:
            try:
                item = self._file_events.get_nowait()
            except queue.Empty:
                break
            events.append({"category": "file_changed", "kwargs": {"name": item["name"]}})

        return events


_triggers: Optional[EventDrivenTriggers] = None


def get_event_driven_triggers() -> EventDrivenTriggers:
    global _triggers
    if _triggers is None:
        _triggers = EventDrivenTriggers()
    return _triggers
