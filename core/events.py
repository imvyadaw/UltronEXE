"""
Events
======
Process-wide pub/sub bus so agents/, plugins/, and ui/ can react to things
happening elsewhere (a tool call, thinking/speaking state) without
importing each other directly.

Wired into main.py: UltronRuntime.run_text/run_voice_typed/run_listen emit()
on it around chat_with_tools()/voice.speak()/tool calls. ui/tray,
ui/dashboard and ui/overlay subscribe() to it to drive their live status -
none of them exist yet as far as main.py or core/brain.py know; the bus
is the only connection.
"""

from typing import Callable, Dict, List, Optional

_bus: Optional["EventBus"] = None


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable):
        self._subscribers.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, **payload):
        for handler in self._subscribers.get(event_name, []):
            try:
                handler(**payload)
            except Exception:
                # A broken UI/plugin subscriber should never take down the
                # assistant loop - same philosophy as the rest of Ultron
                # (a missing optional package degrades a feature, not the app).
                from core.error_trace import log_swallowed as _lsw

                _lsw("core.events.emit")


def get_event_bus() -> EventBus:
    """Process-wide singleton, same pattern as core.brain.get_brain()."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
