"""
real_time_metrics.py
=====================
Live CPU / memory / disk / network snapshot for the dashboard's main
tile - the numbers, refreshed on demand or on a timer.

Dependencies: pip install psutil
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, asdict
from typing import Callable, Optional

import psutil

logger = logging.getLogger("ultron.real_time_metrics")


@dataclass
class SystemSnapshot:
    timestamp: float
    cpu_percent: float
    cpu_per_core: list
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    net_upload_kbps: float
    net_download_kbps: float

    def to_dict(self):
        return asdict(self)


class RealTimeMetrics:
    def __init__(self, disk_path: str = "/", refresh_interval: float = 1.0):
        self.disk_path = disk_path
        self.refresh_interval = refresh_interval
        self._last_net = psutil.net_io_counters()
        self._last_net_time = time.time()
        self._on_tick: Optional[Callable[[SystemSnapshot], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def snapshot(self) -> SystemSnapshot:
        now = time.time()
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(self.disk_path)
        net = psutil.net_io_counters()

        elapsed = max(now - self._last_net_time, 1e-6)
        up_kbps = (net.bytes_sent - self._last_net.bytes_sent) / 1024 / elapsed
        down_kbps = (net.bytes_recv - self._last_net.bytes_recv) / 1024 / elapsed
        self._last_net, self._last_net_time = net, now

        return SystemSnapshot(
            timestamp=now,
            cpu_percent=psutil.cpu_percent(interval=None),
            cpu_per_core=psutil.cpu_percent(interval=None, percpu=True),
            memory_percent=vm.percent,
            memory_used_gb=round(vm.used / (1024**3), 2),
            memory_total_gb=round(vm.total / (1024**3), 2),
            disk_percent=disk.percent,
            disk_used_gb=round(disk.used / (1024**3), 2),
            disk_total_gb=round(disk.total / (1024**3), 2),
            net_upload_kbps=round(up_kbps, 1),
            net_download_kbps=round(down_kbps, 1),
        )

    def on_tick(self, callback: Callable[[SystemSnapshot], None]):
        self._on_tick = callback

    def _loop(self):
        while self._running:
            snap = self.snapshot()
            if self._on_tick:
                self._on_tick(snap)
            time.sleep(self.refresh_interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("RealTimeMetrics streaming every %.1fs", self.refresh_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rtm = RealTimeMetrics()
    rtm.on_tick(
        lambda s: print(
            f"CPU {s.cpu_percent}% | RAM {s.memory_percent}% | "
            f"Net ↑{s.net_upload_kbps}KB/s ↓{s.net_download_kbps}KB/s"
        )
    )
    rtm.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        rtm.stop()
