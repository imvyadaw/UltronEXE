"""
filesystem_watcher.py
======================
Watches directories for create/modify/delete/move events and fires
callbacks, so ULTRON can react to things like "a new file landed in
Downloads" or "the project folder changed".

Dependencies: pip install watchdog
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

logger = logging.getLogger("ultron.filesystem_watcher")


@dataclass
class WatchRule:
    path: str
    recursive: bool = True
    patterns: Optional[List[str]] = None  # e.g. ["*.pdf", "*.docx"]
    ignore_patterns: Optional[List[str]] = None
    on_created: Optional[Callable[[str], None]] = None
    on_modified: Optional[Callable[[str], None]] = None
    on_deleted: Optional[Callable[[str], None]] = None
    on_moved: Optional[Callable[[str, str], None]] = None


class _RuleHandler(FileSystemEventHandler):
    def __init__(self, rule: WatchRule):
        super().__init__()
        self.rule = rule

    def _matches(self, path: str) -> bool:
        if not self.rule.patterns:
            return True
        p = Path(path)
        return any(p.match(pat) for pat in self.rule.patterns)

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._matches(event.src_path) and self.rule.on_created:
            self.rule.on_created(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._matches(event.src_path) and self.rule.on_modified:
            self.rule.on_modified(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and self._matches(event.src_path) and self.rule.on_deleted:
            self.rule.on_deleted(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory and self.rule.on_moved:
            self.rule.on_moved(event.src_path, event.dest_path)


class FilesystemWatcher:
    """Manages multiple watchdog Observers, one set of rules per path."""

    def __init__(self):
        self._observer = Observer()
        self._rules: Dict[str, WatchRule] = {}
        self._started = False

    def watch(self, rule: WatchRule):
        path = str(Path(rule.path).expanduser().resolve())
        if not Path(path).exists():
            logger.error("Watch path does not exist: %s", path)
            return False

        handler = _RuleHandler(rule)
        self._observer.schedule(handler, path, recursive=rule.recursive)
        self._rules[path] = rule
        logger.info("Watching %s (recursive=%s, patterns=%s)", path, rule.recursive, rule.patterns)
        return True

    def start(self):
        if not self._started:
            self._observer.start()
            self._started = True
            logger.info("FilesystemWatcher started (%d watch rules)", len(self._rules))

    def stop(self):
        if self._started:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._started = False
            logger.info("FilesystemWatcher stopped")

    def run_forever(self):
        self.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    watcher = FilesystemWatcher()
    watcher.watch(
        WatchRule(
            path=str(Path.home() / "Downloads"),
            patterns=["*.pdf", "*.zip"],
            on_created=lambda p: print(f"New file: {p}"),
        )
    )
    watcher.run_forever()
