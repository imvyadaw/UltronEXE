"""File watcher trigger
=====================
Watches a file or folder for changes and fires a Ultron tool call when
something happens. Uses the `watchdog` library if installed for
efficient OS-level notifications; otherwise falls back to polling
mtime/listing every poll_interval seconds on a background thread, so
this still works with zero extra dependencies.
"""

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


def _run_tool_action(tool_name: str, arguments: Dict, extra: Dict) -> None:
    try:
        from ai.tool_runtime import execute_tool_call as execute_tool

        args = dict(arguments or {})
        args.update(extra)
        result = execute_tool(tool_name, args)
        print(f"[FileWatcher] Ran '{tool_name}' -> {result}")
    except Exception as e:
        print(f"[FileWatcher] Action '{tool_name}' raised: {e}")


class FileWatcher:
    """Watch paths for filesystem changes and fire a tool call on events."""

    def __init__(self):
        self._watches: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def watch(
        self,
        path: str,
        tool_name: str = None,
        arguments: Dict = None,
        events: Optional[list] = None,
        recursive: bool = False,
        poll_interval: float = 2.0,
    ) -> Dict:
        """Start watching `path`. On a matching filesystem event, runs
        tool_name(arguments) via core.executor (arguments gets an extra
        'changed_path' and 'event_type' field). events filters which kinds
        to react to: any of 'created', 'modified', 'deleted', 'moved'
        (default: all)."""
        target = Path(os.path.expanduser(path))
        if not target.exists():
            return {"error": f"Path does not exist: {target}"}

        watch_id = str(uuid.uuid4())[:8]
        events = events or ["created", "modified", "deleted", "moved"]

        if HAS_WATCHDOG:
            handler = self._make_watchdog_handler(tool_name, arguments, events)
            observer = Observer()
            observer.schedule(handler, str(target), recursive=recursive)
            observer.start()
            with self._lock:
                self._watches[watch_id] = {
                    "path": str(target),
                    "mode": "watchdog",
                    "observer": observer,
                    "tool": tool_name,
                    "arguments": arguments,
                    "events": events,
                }
            return {"success": True, "watch_id": watch_id, "path": str(target), "mode": "watchdog"}

        # Polling fallback
        stop_flag = threading.Event()
        thread = threading.Thread(
            target=self._poll_loop,
            args=(target, tool_name, arguments, recursive, poll_interval, stop_flag),
            daemon=True,
        )
        with self._lock:
            self._watches[watch_id] = {
                "path": str(target),
                "mode": "polling",
                "stop_flag": stop_flag,
                "thread": thread,
                "tool": tool_name,
                "arguments": arguments,
                "events": events,
            }
        thread.start()
        return {"success": True, "watch_id": watch_id, "path": str(target), "mode": "polling"}

    def _make_watchdog_handler(self, tool_name, arguments, events):
        pass

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if "created" in events:
                    _run_tool_action(tool_name, arguments, {"changed_path": event.src_path, "event_type": "created"})

            def on_modified(self, event):
                if "modified" in events:
                    _run_tool_action(tool_name, arguments, {"changed_path": event.src_path, "event_type": "modified"})

            def on_deleted(self, event):
                if "deleted" in events:
                    _run_tool_action(tool_name, arguments, {"changed_path": event.src_path, "event_type": "deleted"})

            def on_moved(self, event):
                if "moved" in events:
                    _run_tool_action(tool_name, arguments, {"changed_path": event.dest_path, "event_type": "moved"})

        return Handler()

    def _poll_loop(self, target: Path, tool_name, arguments, recursive, interval, stop_flag):
        def snapshot():
            if target.is_dir():
                pattern = "**/*" if recursive else "*"
                return {str(p): p.stat().st_mtime for p in target.glob(pattern) if p.is_file()}
            return {str(target): target.stat().st_mtime} if target.exists() else {}

        last = snapshot()
        while not stop_flag.is_set():
            time.sleep(interval)
            current = snapshot()
            for path, mtime in current.items():
                if path not in last:
                    _run_tool_action(tool_name, arguments, {"changed_path": path, "event_type": "created"})
                elif mtime != last[path]:
                    _run_tool_action(tool_name, arguments, {"changed_path": path, "event_type": "modified"})
            for path in last:
                if path not in current:
                    _run_tool_action(tool_name, arguments, {"changed_path": path, "event_type": "deleted"})
            last = current

    def stop_watching(self, watch_id: str) -> Dict:
        with self._lock:
            watch = self._watches.pop(watch_id, None)
        if not watch:
            return {"error": f"No active watch with id '{watch_id}'"}
        if watch["mode"] == "watchdog":
            watch["observer"].stop()
            watch["observer"].join(timeout=2)
        else:
            watch["stop_flag"].set()
        return {"success": True, "stopped": watch_id}

    def list_watches(self) -> Dict:
        with self._lock:
            return {
                "count": len(self._watches),
                "watches": [
                    {"watch_id": wid, "path": w["path"], "mode": w["mode"], "tool": w.get("tool")}
                    for wid, w in self._watches.items()
                ],
            }
