"""
Threshold alerts
================
Turns a proactive/monitors/system_health.py snapshot into a list of
"this crossed a line, tell the user" events - CPU > 90%, battery < 20%
(critical < 10%), memory/disk > 90%. Thresholds intentionally mirror
monitoring/health_check.py's CPU_WARNING_PERCENT / MEMORY_WARNING_PERCENT
/ DISK_WARNING_PERCENT so Ultron's proactive nudge and its "am I
healthy" self-check agree with each other.

Cooldown, not one-shot: once a metric crosses a threshold it re-alerts
at most once per COOLDOWN_SECONDS while it stays over the line (so a
CPU spike that lasts ten minutes doesn't fire ten times), and clears
itself the moment the metric drops back under the threshold, so the
next crossing alerts fresh.
"""

import time
from typing import Dict, List, Optional

from monitoring.health_check import CPU_WARNING_PERCENT, MEMORY_WARNING_PERCENT, DISK_WARNING_PERCENT
from proactive.monitors.system_health import get_system_health_monitor
from proactive.monitors.network_status import get_network_status_monitor
from core.logger import get_logger

logger = get_logger("ultron.proactive.threshold_alerts")

BATTERY_WARNING_PERCENT = 20
BATTERY_CRITICAL_PERCENT = 10
COOLDOWN_SECONDS = 15 * 60  # re-alert on a still-crossed metric at most every 15 min


class ThresholdAlerts:
    """Stateful CPU/RAM/disk/battery/network threshold watcher."""

    def __init__(self):
        self._system = get_system_health_monitor()
        self._network = get_network_status_monitor()
        # metric name -> last time an alert fired while over threshold
        self._last_fired: Dict[str, float] = {}
        # metric name -> currently over threshold (for edge-clearing)
        self._active: Dict[str, bool] = {}

    def _should_fire(self, key: str, is_over: bool) -> bool:
        was_active = self._active.get(key, False)
        self._active[key] = is_over
        if not is_over:
            return False
        now = time.time()
        if not was_active:
            self._last_fired[key] = now
            return True
        if now - self._last_fired.get(key, 0) >= COOLDOWN_SECONDS:
            self._last_fired[key] = now
            return True
        return False

    def check(self) -> List[Dict]:
        """Returns a list of {"category": ..., "kwargs": {...}} events ready
        to be handed to proactive.personality.tone_manager.get_phrase(). Empty
        list means nothing crossed a threshold (or it's still in cooldown)."""
        events: List[Dict] = []

        snapshot = self._system.snapshot()
        if "error" not in snapshot:
            cpu = snapshot.get("cpu_percent", 0)
            if self._should_fire("cpu", cpu >= CPU_WARNING_PERCENT):
                events.append({"category": "cpu_high", "kwargs": {"percent": round(cpu)}})

            mem = snapshot.get("memory_percent", 0)
            if self._should_fire("memory", mem >= MEMORY_WARNING_PERCENT):
                events.append({"category": "memory_high", "kwargs": {"percent": round(mem)}})

            disk = snapshot.get("disk_percent", 0)
            if self._should_fire("disk", disk >= DISK_WARNING_PERCENT):
                events.append({"category": "disk_high", "kwargs": {"percent": round(disk)}})

            battery = snapshot.get("battery")
            if battery and not battery.get("plugged_in", True):
                percent = battery.get("percent", 100)
                if self._should_fire("battery_critical", percent <= BATTERY_CRITICAL_PERCENT):
                    events.append({"category": "battery_critical", "kwargs": {"percent": round(percent)}})
                elif self._should_fire("battery_low", percent <= BATTERY_WARNING_PERCENT):
                    events.append({"category": "battery_low", "kwargs": {"percent": round(percent)}})
                else:
                    # Plugged out but above both thresholds - clear the
                    # critical flag too so a recharge-then-drain cycle
                    # alerts again from scratch.
                    self._active["battery_critical"] = False
            else:
                self._active["battery_low"] = False
                self._active["battery_critical"] = False

        transition = self._network.check_transition()
        if transition is True:
            events.append({"category": "network_restored", "kwargs": {}})
        elif transition is False:
            events.append({"category": "network_down", "kwargs": {}})

        return events


_alerts: Optional[ThresholdAlerts] = None


def get_threshold_alerts() -> ThresholdAlerts:
    global _alerts
    if _alerts is None:
        _alerts = ThresholdAlerts()
    return _alerts
