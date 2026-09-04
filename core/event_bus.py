"""
Event Bus (Phase 21 - Unified Core Architecture)
=================================================
Supersedes core/events.py's plain sync pub/sub for the modules wired
together in Phase 21 (unified_context, action_pipeline, response_manager,
autonomous_engine, goal_manager, user_manager, consciousness). events.py
stays as-is and keeps driving ui/tray, ui/dashboard, ui/overlay - nothing
there needs to change. This module is additive: it adds three things
events.py doesn't have, and forwards every emit() to the legacy bus
best-effort so existing subscribers keep working without rewiring.

New here:
  - async handlers: a coroutine subscriber gets awaited if a loop is
    already running, otherwise run to completion via asyncio.run().
  - wildcard subscription ("*") - a debug console or consciousness.py
    can watch everything without enumerating event names.
  - bounded history - the last MAX_HISTORY emitted events (name, payload
    keys, timestamp), so a caller can answer "what just happened" without
    its own bookkeeping.

Usage:
    from core.event_bus import get_event_bus
    bus = get_event_bus()
    bus.subscribe("action.completed", on_action_done)
    bus.emit("action.completed", action="open_application", success=True)
"""

import asyncio
import inspect
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.event_bus")

MAX_HISTORY = 200


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()
        self._history: Deque[Dict] = deque(maxlen=MAX_HISTORY)

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """event_name="*" receives every event, sync or async handler."""
        with self._lock:
            self._subscribers.setdefault(event_name, []).append(handler)

    def unsubscribe(self, event_name: str, handler: Callable) -> bool:
        with self._lock:
            handlers = self._subscribers.get(event_name, [])
            if handler in handlers:
                handlers.remove(handler)
                return True
        return False

    def emit(self, event_name: str, **payload: Any) -> None:
        self._history.append(
            {
                "event": event_name,
                "keys": list(payload.keys()),
                "timestamp": time.time(),
            }
        )
        for handler in self._handlers_for(event_name):
            self._dispatch(handler, event_name, payload)
        self._forward_to_legacy_bus(event_name, payload)

    # -- internals ---------------------------------------------------------
    def _handlers_for(self, event_name: str) -> List[Callable]:
        with self._lock:
            return list(self._subscribers.get(event_name, [])) + list(self._subscribers.get("*", []))

    def _dispatch(self, handler: Callable, event_name: str, payload: Dict) -> None:
        try:
            if inspect.iscoroutinefunction(handler):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(handler(**payload))
                except RuntimeError:
                    asyncio.run(handler(**payload))
            else:
                handler(**payload)
        except Exception:
            # A broken subscriber never takes down the emitter - same
            # philosophy as core/events.py.
            logger.exception(f"event_bus subscriber failed for '{event_name}'")

    def _forward_to_legacy_bus(self, event_name: str, payload: Dict) -> None:
        """Best-effort: anything still listening on core.events keeps working."""
        try:
            from core.events import get_event_bus as get_legacy_bus

            get_legacy_bus().emit(event_name, **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.event_bus._forward_to_legacy_bus")

    def recent_events(self, limit: int = 20) -> List[Dict]:
        return list(self._history)[-limit:]


_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus
