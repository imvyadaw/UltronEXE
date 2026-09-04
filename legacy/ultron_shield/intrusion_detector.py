"""
intrusion_detector.py
====================
Watches a stream of security-relevant events you feed it - failed
pairing attempts, failed device auth, ungranted remote-command
attempts, biometric mismatches - and raises `IntrusionEvent`s when
they cross a rate or pattern threshold (e.g. 5 failed auths from the
same source in a minute).

This module only *detects and reports*; it does not itself block
network traffic, ban IPs, or kill processes. The one exception is a
purely local, reversible `is_locked_out()` cooldown keyed to a source
identifier (device_id, IP, whatever you pass), which existing auth
code (e.g. `device_manager.authenticate`) can consult before
accepting a new attempt - that's the extent of the "enforcement"
here, and it always expires on its own.

Pure standard library.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Callable, Deque, Dict, List, Optional

logger = logging.getLogger("ultron.intrusion_detector")


class Severity(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


@dataclass
class IntrusionEvent:
    kind: str
    source: str
    severity: Severity
    detail: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class _RuleState:
    window_seconds: float
    threshold: int
    severity: Severity
    lockout_seconds: float
    timestamps: Deque[float] = field(default_factory=deque)


AlertCallback = Callable[[IntrusionEvent], None]


class IntrusionDetector:
    """Rate-based detector over named event kinds (e.g. "auth_failure",
    "ungranted_command", "biometric_mismatch"), each with its own window/
    threshold/lockout policy."""

    def __init__(self):
        self._rules: Dict[str, _RuleState] = {}
        self._per_source: Dict[str, Dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(deque))
        self._lockouts: Dict[str, float] = {}  # source -> lockout_expiry_ts
        self._callbacks: List[AlertCallback] = []

    def define_rule(
        self,
        kind: str,
        window_seconds: float,
        threshold: int,
        severity: Severity = Severity.MEDIUM,
        lockout_seconds: float = 0,
    ) -> None:
        """e.g. define_rule("auth_failure", window_seconds=60, threshold=5,
        severity=Severity.HIGH, lockout_seconds=300)"""
        self._rules[kind] = _RuleState(
            window_seconds=window_seconds, threshold=threshold, severity=severity, lockout_seconds=lockout_seconds
        )
        logger.info("Defined intrusion rule '%s': %d in %ss -> %s", kind, threshold, window_seconds, severity.name)

    def on_alert(self, callback: AlertCallback) -> None:
        self._callbacks.append(callback)

    def record_event(self, kind: str, source: str, detail: str = "") -> Optional[IntrusionEvent]:
        """Feed one occurrence of a defined event kind. Returns an
        IntrusionEvent if this occurrence pushed the source over threshold."""
        rule = self._rules.get(kind)
        if not rule:
            logger.debug("record_event for undefined rule kind '%s' - ignored", kind)
            return None

        now = time.time()
        timestamps = self._per_source[source][kind]
        timestamps.append(now)
        cutoff = now - rule.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) < rule.threshold:
            return None

        event = IntrusionEvent(
            kind=kind,
            source=source,
            severity=rule.severity,
            detail=detail or f"{len(timestamps)} '{kind}' events in " f"{rule.window_seconds}s from {source}",
        )
        if rule.lockout_seconds > 0:
            self._lockouts[source] = now + rule.lockout_seconds
            logger.warning("Locking out '%s' for %ss after '%s' threshold breach", source, rule.lockout_seconds, kind)

        timestamps.clear()  # avoid re-firing every subsequent event until it re-accumulates
        self._emit(event)
        return event

    def is_locked_out(self, source: str) -> bool:
        expiry = self._lockouts.get(source)
        if expiry is None:
            return False
        if time.time() >= expiry:
            del self._lockouts[source]
            return False
        return True

    def lockout_remaining_seconds(self, source: str) -> float:
        expiry = self._lockouts.get(source)
        if expiry is None:
            return 0.0
        return max(0.0, expiry - time.time())

    def clear_lockout(self, source: str) -> None:
        self._lockouts.pop(source, None)

    def _emit(self, event: IntrusionEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Intrusion alert callback raised")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detector = IntrusionDetector()
    detector.define_rule("auth_failure", window_seconds=60, threshold=3, severity=Severity.HIGH, lockout_seconds=30)

    def alert_handler(event: IntrusionEvent):
        print(f"ALERT [{event.severity.name}] {event.kind} from {event.source}: {event.detail}")

    detector.on_alert(alert_handler)

    for _ in range(3):
        detector.record_event("auth_failure", source="192.168.1.50", detail="bad token")

    print("Locked out?", detector.is_locked_out("192.168.1.50"))
    print("Remaining:", round(detector.lockout_remaining_seconds("192.168.1.50"), 1), "s")
