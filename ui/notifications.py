"""
ui.notifications - shared notification/error surface for every UI module.

Phase 13: dashboard, overlay, tray, and orb already had an "error" color
defined in their state palettes, but nothing in the codebase ever emitted
one - core.events has no producer of an "error" event, and voice_ui's
AvatarController (which also defines ERROR) isn't wired to core.events at
all. This module is the missing piece: a single place any UI surface (or
ui/bridge.py, on a core.assistant failure) calls to raise a user-facing
notification, which:

    1. Is kept in a small in-memory ring buffer (`get_recent`) so a
       surface that opens late (web_ui polling, a freshly-opened
       dashboard) can catch up instead of only seeing new ones.
    2. Is re-broadcast on core.events as "notification" (always) and
       "error" (when level == "error") so every subscriber - tray,
       dashboard, overlay, orb, voice_ui's avatar bridge - reacts the
       same way they already react to thinking_start/response_ready/etc.

No new dependency; same "optional feature, never crashes the app"
philosophy as the rest of ui/.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

from core.events import get_event_bus
from core.logger import get_logger

logger = get_logger("ultron.ui.notifications")

LEVELS = ("info", "warning", "error")
MAX_HISTORY = 200


@dataclass
class Notification:
    id: str
    level: str
    title: str
    message: str
    source: str
    timestamp: float = field(default_factory=time.time)
    image_path: Optional[str] = None

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp,
            "image_path": self.image_path,
        }


_history: Deque[Notification] = deque(maxlen=MAX_HISTORY)

# Callers (e.g. security/intruder_alert.py) sometimes use a level name
# that isn't one of the three canonical LEVELS - normalize those instead
# of silently downgrading them to "info".
_LEVEL_ALIASES = {"critical": "error", "crit": "error", "warn": "warning"}


def notify(
    title: str, message: str = "", level: str = "info", source: str = "ultron", image_path: Optional[str] = None
) -> Notification:
    """Raise a notification visible to every UI surface. Safe to call
    from any thread - core.events.EventBus.emit() and deque.append()
    are both fine off the main thread; individual subscribers (Tk
    windows) marshal onto their own thread via TkWindow.post()."""
    level = _LEVEL_ALIASES.get(level, level)
    if level not in LEVELS:
        level = "info"

    n = Notification(
        id=str(uuid.uuid4()), level=level, title=title, message=message, source=source, image_path=image_path
    )
    _history.append(n)

    log = {"info": logger.info, "warning": logger.warning, "error": logger.error}[level]
    log(f"[{source}] {title}: {message}" if message else f"[{source}] {title}")

    bus = get_event_bus()
    bus.emit("notification", **n.to_json())
    if level == "error":
        bus.emit("error", text=message or title, source=source)

    return n


def report_error(message: str, source: str = "ultron", title: str = "Error") -> Notification:
    """Convenience wrapper - the common case of notify(level='error')."""
    return notify(title=title, message=message, level="error", source=source)


def get_recent(limit: int = 20, level: Optional[str] = None) -> List[dict]:
    items = list(_history)
    if level:
        items = [n for n in items if n.level == level]
    return [n.to_json() for n in items[-limit:]]


def clear() -> None:
    _history.clear()


class NotificationHub:
    """Thin object wrapper around this module's functions, for callers
    (security/intruder_alert.py) that expect a hub instance with
    .notify()/.report_error()/.get_recent()/.clear() rather than bare
    module-level functions."""

    def notify(
        self,
        title: str,
        message: str = "",
        level: str = "info",
        source: str = "ultron",
        image_path: Optional[str] = None,
    ) -> Notification:
        return notify(title=title, message=message, level=level, source=source, image_path=image_path)

    def report_error(self, message: str, source: str = "ultron", title: str = "Error") -> Notification:
        return report_error(message=message, source=source, title=title)

    def get_recent(self, limit: int = 20, level: Optional[str] = None) -> List[dict]:
        return get_recent(limit=limit, level=level)

    def clear(self) -> None:
        clear()


_hub: Optional["NotificationHub"] = None


def get_notification_hub() -> "NotificationHub":
    """Process-wide singleton, same pattern as core.brain.get_brain() /
    core.events.get_event_bus(). Was missing before, which meant
    security/intruder_alert.py's `from ui.notifications import
    get_notification_hub` silently failed every time."""
    global _hub
    if _hub is None:
        _hub = NotificationHub()
    return _hub
