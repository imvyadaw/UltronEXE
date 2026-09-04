"""
System health monitor
======================
Point-in-time "is the machine under strain" snapshot for the proactive
engine - CPU/RAM/disk (delegated to monitoring/resource_monitor.py, the
same source monitoring/health_check.py already uses, so Ultron never
reports two different CPU numbers to the user) plus battery, which
resource_monitor.py doesn't cover.

Deliberately dumb: no thresholds, no "should I alert" logic here - that
belongs to proactive/triggers/threshold_alerts.py. This module only
answers "what is the number right now".
"""

from typing import Dict, Optional

import psutil

from monitoring.resource_monitor import get_resource_monitor
from core.logger import get_logger

logger = get_logger("ultron.proactive.system_health")


class SystemHealthMonitor:
    """Snapshot of CPU/RAM/disk/battery for the machine Ultron runs on."""

    def __init__(self):
        self._resource_monitor = get_resource_monitor()

    def _battery(self) -> Optional[Dict]:
        """Best-effort battery reading. Returns None on desktops or any
        platform where psutil can't see a battery - never raises."""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return None
            return {
                "percent": battery.percent,
                "plugged_in": bool(battery.power_plugged),
                "secs_left": None if battery.secsleft in (psutil.POWER_TIME_UNLIMITED, -1) else battery.secsleft,
            }
        except Exception as e:
            logger.debug(f"Battery read unavailable: {e}")
            return None

    def snapshot(self) -> Dict:
        """CPU/RAM/disk (from monitoring.resource_monitor) + battery, in one dict."""
        reading = self._resource_monitor.snapshot()
        if "error" in reading:
            return {"error": reading["error"]}
        reading["battery"] = self._battery()
        return reading

    def top_processes(self, by: str = "cpu", limit: int = 5) -> Dict:
        """Pass-through to resource_monitor - useful context once a threshold
        alert has already decided CPU/RAM is worth mentioning."""
        return self._resource_monitor.top_processes(by=by, limit=limit)


_monitor: Optional[SystemHealthMonitor] = None


def get_system_health_monitor() -> SystemHealthMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SystemHealthMonitor()
    return _monitor
