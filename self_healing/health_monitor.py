"""
health_monitor.py
====================
Periodically checks system + ULTRON-process health (CPU, RAM, disk
free space, and optional custom probes like "is the STT engine
responding") against configurable thresholds, and fires callbacks
when something crosses into warning/critical territory. This is the
sensor layer for SELF_HEALING - auto_recovery.py decides what to do
about the alerts this module raises.

Dependencies: pip install psutil
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

import psutil

logger = logging.getLogger("ultron.health_monitor")


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class HealthAlert:
    metric: str
    severity: Severity
    value: float
    threshold: float
    message: str
    timestamp: str


@dataclass
class Thresholds:
    cpu_warning: float = 80.0
    cpu_critical: float = 95.0
    memory_warning: float = 80.0
    memory_critical: float = 95.0
    disk_warning: float = 85.0
    disk_critical: float = 95.0


class HealthMonitor:
    """Polls system metrics and custom probes, raising alerts on threshold breaches."""

    def __init__(self, thresholds: Optional[Thresholds] = None, disk_path: str = "C:\\"):
        self.thresholds = thresholds or Thresholds()
        self.disk_path = disk_path
        self._probes: Dict[str, Callable[[], bool]] = {}  # name -> healthy?()
        self._alert_callbacks: List[Callable[[HealthAlert], None]] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def register_probe(self, name: str, probe_fn: Callable[[], bool]):
        """Register a custom health probe, e.g. `lambda: stt_engine.ping()`."""
        self._probes[name] = probe_fn

    def on_alert(self, callback: Callable[[HealthAlert], None]):
        self._alert_callbacks.append(callback)

    def _emit(self, alert: HealthAlert):
        log_fn = logger.warning if alert.severity == Severity.WARNING else logger.error
        log_fn(
            "[%s] %s = %.1f (threshold %.1f): %s",
            alert.severity.value,
            alert.metric,
            alert.value,
            alert.threshold,
            alert.message,
        )
        for cb in self._alert_callbacks:
            try:
                cb(alert)
            except Exception as exc:
                logger.error("Health alert callback failed: %s", exc)

    def check_once(self) -> List[HealthAlert]:
        alerts: List[HealthAlert] = []
        now = datetime.now().isoformat(timespec="seconds")
        t = self.thresholds

        cpu = psutil.cpu_percent(interval=0.3)
        alerts += self._threshold_check("cpu_percent", cpu, t.cpu_warning, t.cpu_critical, "CPU usage is high", now)

        mem = psutil.virtual_memory().percent
        alerts += self._threshold_check(
            "memory_percent", mem, t.memory_warning, t.memory_critical, "Memory usage is high", now
        )

        try:
            disk = psutil.disk_usage(self.disk_path).percent
            alerts += self._threshold_check(
                "disk_percent", disk, t.disk_warning, t.disk_critical, f"Disk {self.disk_path} is getting full", now
            )
        except OSError as exc:
            logger.warning("Could not check disk usage for %s: %s", self.disk_path, exc)

        for name, probe in self._probes.items():
            try:
                healthy = probe()
            except Exception as exc:
                healthy = False
                logger.error("Probe '%s' raised an exception: %s", name, exc)
            if not healthy:
                alert = HealthAlert(
                    metric=name,
                    severity=Severity.CRITICAL,
                    value=0.0,
                    threshold=1.0,
                    message=f"Probe '{name}' reported unhealthy",
                    timestamp=now,
                )
                alerts.append(alert)

        for alert in alerts:
            self._emit(alert)
        return alerts

    def _threshold_check(self, metric, value, warn, crit, message, now) -> List[HealthAlert]:
        if value >= crit:
            return [HealthAlert(metric, Severity.CRITICAL, value, crit, message, now)]
        if value >= warn:
            return [HealthAlert(metric, Severity.WARNING, value, warn, message, now)]
        return []

    def start(self, interval_seconds: float = 30.0):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _loop():
            while not self._stop_event.is_set():
                self.check_once()
                self._stop_event.wait(interval_seconds)

        self._thread = threading.Thread(target=_loop, daemon=True, name="HealthMonitorLoop")
        self._thread.start()
        logger.info("Health monitor started (interval=%.0fs)", interval_seconds)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Health monitor stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor = HealthMonitor()
    for a in monitor.check_once():
        print(a)
    if not monitor.check_once():
        print("All metrics currently within thresholds.")
