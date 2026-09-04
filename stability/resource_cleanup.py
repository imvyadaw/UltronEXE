"""
Resource cleanup registry
==========================
Ultron opens a lot of things over its lifetime that need an explicit close:
DB connections (`database/`), browser driver sessions (`browser/*`),
camera/mic handles (`vision/`, `voice/`), file watchers
(`PHASE_17_6_AUTOMATION/DEEP_OS_INTEGRATION/filesystem_watcher.py`), etc.
Today each of those modules is responsible for its own cleanup, called (if
at all) from whatever code happened to construct it - there's no single
place that guarantees "on shutdown, everything gets a chance to close",
which is how you get orphaned Chrome driver processes or a locked sqlite
file surviving a crash.

This module is that one place: a process-wide registry any module can
register a cleanup callback with, plus one `shutdown_all()` entry point
that's registered with `atexit` and safe to call more than once (idempotent)
or call manually (e.g. from a signal handler, or a test's teardown).

Usage
-----
    from stability.resource_cleanup import register_cleanup

    class ChromeController:
        def __init__(self):
            self._driver = ...
            self._cleanup_handle = register_cleanup(
                f"chrome_driver_{id(self)}", self._driver.quit
            )

        def close(self):
            self._cleanup_handle.run_now()  # runs it and deregisters

Design match with the rest of the codebase: every cleanup call is wrapped
the same way `core/error_handler.py`'s `run_safely()` wraps tool calls - one
resource failing to close is logged, never lets the exception stop the rest
of shutdown from running (same "degrade, don't crash" principle as
integration and core/startup.py).
"""

from __future__ import annotations

import atexit
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List

try:
    from core.logger import get_logger

    _logger = get_logger("ultron.stability.resource_cleanup")
except Exception:  # pragma: no cover - keep this module usable standalone
    import logging

    _logger = logging.getLogger("ultron.stability.resource_cleanup")


@dataclass
class CleanupHandle:
    name: str
    _fn: Callable[[], None]
    _registry: "ResourceRegistry"
    _done: bool = field(default=False, init=False)

    def run_now(self) -> bool:
        """Run this one cleanup immediately and deregister it. Returns True
        on success, False if it raised (the error is logged, not raised)."""
        return self._registry._run_one(self)

    @property
    def done(self) -> bool:
        return self._done


class ResourceRegistry:
    """Process-wide registry of cleanup callbacks. Not meant to be
    instantiated directly by callers - use the module-level functions
    below, which share one instance (`_registry`)."""

    def __init__(self):
        self._handles: Dict[str, CleanupHandle] = {}
        self._lock = threading.Lock()
        self._shutdown_started = False

    def register(self, name: str, cleanup_fn: Callable[[], None]) -> CleanupHandle:
        handle = CleanupHandle(name=name, _fn=cleanup_fn, _registry=self)
        with self._lock:
            # A name collision (e.g. a singleton re-created after a prior
            # close()) replaces the old entry rather than accumulating dead
            # handles forever.
            self._handles[name] = handle
        return handle

    def _run_one(self, handle: CleanupHandle) -> bool:
        with self._lock:
            if handle.done:
                return True
            self._handles.pop(handle.name, None)
        try:
            handle._fn()
            handle._done = True
            return True
        except Exception as e:
            handle._done = True  # still mark done - don't retry a broken cleanup forever
            _logger.warning(f"cleanup '{handle.name}' raised during shutdown: {e}")
            return False

    def shutdown_all(self) -> Dict[str, bool]:
        """Run every still-pending cleanup, most-recently-registered first
        (LIFO - mirrors how resources are usually opened in dependency
        order, so the last thing opened is the first thing closed).
        Idempotent: a second call only touches whatever was registered
        since the first call finished."""
        with self._lock:
            if self._shutdown_started:
                pass  # allow re-entry; still process anything registered since
            self._shutdown_started = True
            pending = list(reversed(list(self._handles.values())))
        results = {}
        for handle in pending:
            results[handle.name] = self._run_one(handle)
        return results

    def status(self) -> List[dict]:
        with self._lock:
            return [{"name": h.name, "done": h.done} for h in self._handles.values()]


_registry = ResourceRegistry()
_atexit_registered = False
_atexit_lock = threading.Lock()


def register_cleanup(name: str, cleanup_fn: Callable[[], None]) -> CleanupHandle:
    """Register a zero-arg cleanup callback under `name`. Also lazily
    registers the process-wide `shutdown_all()` with `atexit` on first use,
    so a script that never explicitly calls shutdown still gets a
    best-effort cleanup pass on normal interpreter exit."""
    global _atexit_registered
    if not _atexit_registered:
        with _atexit_lock:
            if not _atexit_registered:
                atexit.register(shutdown_all)
                _atexit_registered = True
    return _registry.register(name, cleanup_fn)


def shutdown_all() -> Dict[str, bool]:
    """Run all pending cleanups now. Safe to call multiple times, and safe
    to call from an atexit hook, a signal handler, or a test teardown."""
    return _registry.shutdown_all()


def status() -> List[dict]:
    """What's currently registered and pending, for a health/debug endpoint."""
    return _registry.status()
