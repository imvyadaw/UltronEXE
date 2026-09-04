"""
Network status monitor
=======================
Thin proactive-facing wrapper around core/internet_monitor.py (the same
cached connectivity check ai/ai_router.py already uses to pick cloud vs
local per turn) - just adds transition tracking, so
triggers/threshold_alerts.py can fire "internet just dropped" /
"internet's back" exactly once per transition instead of every poll.
"""

import time
from typing import Dict, Optional

from core.internet_monitor import is_online
from core.logger import get_logger

logger = get_logger("ultron.proactive.network_status")


class NetworkStatusMonitor:
    """Cached online/offline state + transition detection."""

    def __init__(self):
        self._last_state: Optional[bool] = None

    def snapshot(self) -> Dict:
        try:
            online = is_online()
        except Exception as e:
            logger.debug(f"Connectivity check failed: {e}")
            online = False
        return {"timestamp": time.time(), "online": online}

    def check_transition(self) -> Optional[bool]:
        """Returns True if the connection just came back online, False if
        it just went offline, or None if nothing changed since the last
        call. Stateful - poll from one place (the proactive engine loop)."""
        online = self.snapshot()["online"]
        transitioned = None
        if self._last_state is not None and online != self._last_state:
            transitioned = online
        self._last_state = online
        return transitioned


_monitor: Optional[NetworkStatusMonitor] = None


def get_network_status_monitor() -> NetworkStatusMonitor:
    global _monitor
    if _monitor is None:
        _monitor = NetworkStatusMonitor()
    return _monitor
