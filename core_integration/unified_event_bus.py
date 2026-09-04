"""
Unified event bus
==================
core.events.EventBus (Phase 9) is process-wide pub/sub already used by
main.py, ui/tray, ui/dashboard, ui/overlay and proactive/engine.py. It is
NOT replaced here - UnifiedEventBus *wraps* the same singleton instance
(core.events.get_event_bus()) so every existing emit()/subscribe() call
in the Phase 16 codebase keeps working, completely unaware this file
exists.

What this adds on top, for Phase 17 code only:
    - namespaced/wildcard subscriptions   ("plugin:*", "phase16:*", "*")
    - a capped in-memory history so a late subscriber (e.g. a dashboard
      panel that opens after the event already fired) can call
      replay(event_name) instead of missing it
    - subscribe() returns an unsubscribe callable instead of nothing
    - emit() never raises - same "a broken subscriber degrades a
      feature, not the app" philosophy as core.events.EventBus

Every emit() made through this wrapper is *also* forwarded to the legacy
bus's own subscribers, so old-style exact-name subscribers (ui/tray,
ui/dashboard, ...) and new-style wildcard subscribers see the exact same
events - there is only one bus, this is just a richer front door onto it.
"""

import fnmatch
from collections import deque
from threading import Lock
from typing import Callable, Deque, List, Optional, Tuple

from core.events import EventBus, get_event_bus

DEFAULT_HISTORY_SIZE = 200

_unified_bus: Optional["UnifiedEventBus"] = None
_lock = Lock()


class UnifiedEventBus:
    """Wraps core.events.EventBus - never constructed with a bus of its
    own, always the shared Phase 16 singleton, so this stays a strict
    superset rather than a second source of truth."""

    def __init__(self, legacy_bus: Optional[EventBus] = None, history_size: int = DEFAULT_HISTORY_SIZE):
        self._legacy = legacy_bus if legacy_bus is not None else get_event_bus()
        self._wildcard_subscribers: List[Tuple[str, Callable]] = []
        self._history: Deque[Tuple[str, dict]] = deque(maxlen=history_size)
        self._history_lock = Lock()

    # -- legacy passthrough (exact-name subscribers, unchanged shape) -----
    def subscribe(self, pattern: str, handler: Callable) -> Callable[[], None]:
        """Subscribe to an exact event name or a fnmatch-style wildcard
        pattern ("ui:*", "*"). Exact names with no '*' are also
        registered on the legacy bus directly, so Phase 16 code reading
        core.events.get_event_bus()._subscribers keeps seeing them.
        Returns an unsubscribe function.
        """
        if "*" in pattern or "?" in pattern:
            entry = (pattern, handler)
            self._wildcard_subscribers.append(entry)

            def _unsubscribe():
                if entry in self._wildcard_subscribers:
                    self._wildcard_subscribers.remove(entry)

            return _unsubscribe

        self._legacy.subscribe(pattern, handler)

        def _unsubscribe():
            handlers = self._legacy._subscribers.get(pattern, [])
            if handler in handlers:
                handlers.remove(handler)

        return _unsubscribe

    def emit(self, event_name: str, **payload) -> None:
        """Fan out to: (1) the legacy bus's exact-name subscribers -
        this is what makes it "unified" rather than a parallel bus -
        and (2) any wildcard subscribers registered here. Also records
        the event in history. Never raises - same best-effort contract
        as core.events.EventBus.emit()."""
        with self._history_lock:
            self._history.append((event_name, dict(payload)))

        try:
            self._legacy.emit(event_name, **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core_integration.unified_event_bus.emit")

        for pattern, handler in list(self._wildcard_subscribers):
            if fnmatch.fnmatch(event_name, pattern):
                try:
                    handler(event_name=event_name, **payload)
                except Exception:
                    # A broken wildcard subscriber never takes down the
                    # emitting call site.
                    from core.error_trace import log_swallowed as _lsw

                    _lsw("core_integration.unified_event_bus.emit")

    # -- history / replay --------------------------------------------------
    def replay(self, pattern: str = "*", limit: Optional[int] = None) -> List[Tuple[str, dict]]:
        """Return past (event_name, payload) pairs matching `pattern`,
        oldest first, for a late subscriber to catch up on. Does not
        re-fire any handlers - the caller decides what to do with them."""
        with self._history_lock:
            matches = [(n, p) for n, p in self._history if fnmatch.fnmatch(n, pattern)]
        if limit is not None:
            matches = matches[-limit:]
        return matches

    def clear_history(self) -> None:
        with self._history_lock:
            self._history.clear()

    @property
    def legacy_bus(self) -> EventBus:
        """Escape hatch back to the raw core.events.EventBus instance,
        for code that specifically needs the Phase 16 object identity."""
        return self._legacy


def get_unified_bus() -> UnifiedEventBus:
    """Process-wide singleton, same pattern as core.events.get_event_bus()
    and core.brain.get_brain(). Always wraps the one legacy bus instance."""
    global _unified_bus
    with _lock:
        if _unified_bus is None:
            _unified_bus = UnifiedEventBus()
        return _unified_bus
