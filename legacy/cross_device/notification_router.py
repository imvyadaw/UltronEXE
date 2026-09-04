"""
notification_router.py
====================
Decides which paired device(s) a given notification should reach, and
in what form. Pure decision + delivery-tracking logic - it calls out
to `CompanionWebSocketServer.send_to_device` / `.broadcast` to actually
deliver, and to `DeviceManager` to know who's registered for what.

Rules are opt-in and local: quiet hours, per-device capability
filtering, and de-duplication of the same notification fired twice in
a short window. Nothing here decides on its own to notify a device
that wasn't already registered with the "notifications" capability.

Pure standard library.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, time as dtime
from enum import IntEnum
from typing import Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("ultron.notification_router")

DEFAULT_LOG_PATH = "ultron_data/cross_device/notification_log.json"
DEDUPE_WINDOW_SECONDS = 60
MAX_LOG_ENTRIES = 500


class Priority(IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3  # bypasses quiet hours


@dataclass
class Notification:
    title: str
    body: str
    priority: Priority = Priority.NORMAL
    source: str = "ultron"
    require_capability: str = "notifications"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def fingerprint(self) -> str:
        raw = f"{self.title}|{self.body}|{self.source}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority.value
        return d


@dataclass
class QuietHours:
    start: dtime = dtime(22, 0)
    end: dtime = dtime(7, 0)

    def is_active(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        t = now.time()
        if self.start <= self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end  # wraps past midnight


SendFn = Callable[[dict, Optional[str]], Awaitable[int]]  # (message, capability) -> sent_count


class NotificationRouter:
    """Routes Notification objects to devices via an injected send function
    (normally `CompanionWebSocketServer.broadcast`)."""

    def __init__(self, send_fn: SendFn, quiet_hours: Optional[QuietHours] = None, log_path: str = DEFAULT_LOG_PATH):
        self.send_fn = send_fn
        self.quiet_hours = quiet_hours or QuietHours()
        self.log_path = log_path
        self._recent: Dict[str, float] = {}  # fingerprint -> last_sent_ts
        self._log: List[dict] = []
        self._load_log()

    async def route(self, notification: Notification) -> int:
        """Send a notification out. Returns how many devices it reached
        (0 if suppressed by dedupe/quiet-hours, or if nothing's connected)."""
        fp = notification.fingerprint()
        now_ts = time.time()

        last_sent = self._recent.get(fp)
        if last_sent and (now_ts - last_sent) < DEDUPE_WINDOW_SECONDS:
            logger.info("Suppressed duplicate notification: %s", notification.title)
            return 0

        if notification.priority < Priority.URGENT and self.quiet_hours.is_active():
            logger.info("Suppressed by quiet hours: %s", notification.title)
            self._append_log(notification, sent_to=0, suppressed_reason="quiet_hours")
            return 0

        message = {"type": "notification", **notification.to_dict()}
        sent = await self.send_fn(message, notification.require_capability)

        self._recent[fp] = now_ts
        self._append_log(notification, sent_to=sent, suppressed_reason=None)
        return sent

    def _append_log(self, notification: Notification, sent_to: int, suppressed_reason: Optional[str]) -> None:
        entry = notification.to_dict()
        entry["sent_to"] = sent_to
        entry["suppressed_reason"] = suppressed_reason
        self._log.append(entry)
        self._log = self._log[-MAX_LOG_ENTRIES:]
        self._save_log()

    def history(self, limit: int = 50) -> List[dict]:
        return self._log[-limit:]

    def _load_log(self) -> None:
        if not os.path.exists(self.log_path):
            return
        try:
            with open(self.log_path, "r") as f:
                self._log = json.load(f).get("entries", [])
        except (json.JSONDecodeError, OSError):
            self._log = []

    def _save_log(self) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w") as f:
            json.dump({"entries": self._log}, f, indent=2)


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def _fake_send(message, capability):
        print(f"Would send to devices with '{capability}':", message)
        return 1

    async def _demo():
        router = NotificationRouter(_fake_send, log_path="ultron_data/cross_device/_demo_log.json")
        await router.route(Notification(title="Build finished", body="Phase 17.8 compiled cleanly."))
        await router.route(Notification(title="Build finished", body="Phase 17.8 compiled cleanly."))
        print("History:", router.history())

    asyncio.run(_demo())
