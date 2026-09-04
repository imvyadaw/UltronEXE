"""
Resource monitor
================
System resource snapshots (CPU, RAM, disk) for the machine Ultron runs
on - "how loaded is my PC right now", and the data source
monitoring/health_check.py and monitoring/alerts.py build on. Uses
psutil, already a hard dependency of the project (see
windows/services/services.py, requirements.txt) - unlike some other
optional-dependency modules in this codebase, no fallback path is
needed here since psutil is already required.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional

import psutil

_DEFAULT_DISK_PATH = str(Path.home().anchor or "/")


class ResourceMonitor:
    """Point-in-time and rolling snapshots of CPU/RAM/disk usage."""

    def __init__(self, history_size: int = 60):
        self._history_size = history_size
        self._history: List[Dict] = []

    def snapshot(self, disk_path: str = None) -> Dict:
        """One-off reading of current CPU/RAM/disk usage."""
        try:
            disk_path = disk_path or _DEFAULT_DISK_PATH
            cpu_percent = psutil.cpu_percent(interval=0.2)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage(disk_path)

            reading = {
                "timestamp": time.time(),
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
            }

            self._history.append(reading)
            if len(self._history) > self._history_size:
                self._history.pop(0)

            return reading
        except Exception as e:
            return {"error": str(e)}

    def top_processes(self, by: str = "cpu", limit: int = 5) -> Dict:
        """Top processes by CPU or memory usage - `by` is 'cpu' or 'memory'."""
        try:
            metric_key = "cpu_percent" if by == "cpu" else "memory_percent"
            processes = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            processes.sort(key=lambda p: p.get(metric_key) or 0, reverse=True)
            return {"by": by, "processes": processes[:limit]}
        except Exception as e:
            return {"error": str(e)}

    def history_summary(self) -> Dict:
        """Average CPU/memory/disk usage over the retained rolling window."""
        if not self._history:
            return {"count": 0}
        try:
            count = len(self._history)
            return {
                "count": count,
                "avg_cpu_percent": round(sum(r["cpu_percent"] for r in self._history) / count, 2),
                "avg_memory_percent": round(sum(r["memory_percent"] for r in self._history) / count, 2),
                "avg_disk_percent": round(sum(r["disk_percent"] for r in self._history) / count, 2),
                "window_seconds": round(self._history[-1]["timestamp"] - self._history[0]["timestamp"], 1),
            }
        except Exception as e:
            return {"error": str(e)}


_monitor: Optional[ResourceMonitor] = None


def get_resource_monitor() -> ResourceMonitor:
    global _monitor
    if _monitor is None:
        _monitor = ResourceMonitor()
    return _monitor
