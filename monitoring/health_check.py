"""
Health check
============
One place to ask "is Ultron actually healthy right now" - aggregates
checks across the pieces that can silently fail: internet/cloud AI
reachability (core/internet_monitor.py, ai/ai_router.py), resource
pressure (monitoring/resource_monitor.py), and disk space for the
SQLite-backed memory stores. Returns one overall status plus the
per-check detail, so monitoring/alerts.py (or a future "ultron, are you
okay?" voice command) has a single well-shaped thing to check.
"""

import shutil
import time
from pathlib import Path
from typing import Callable, Dict, List

from core.internet_monitor import is_online
from monitoring.resource_monitor import get_resource_monitor

STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage"

# Thresholds are intentionally simple/conservative - tune per-deployment
# via monitoring/alerts.py's AlertRule objects instead of hardcoding more here.
CPU_WARNING_PERCENT = 90
MEMORY_WARNING_PERCENT = 90
DISK_WARNING_PERCENT = 90
MIN_FREE_DISK_GB = 1.0


def _check_internet() -> Dict:
    try:
        online = is_online()
        return {"name": "internet", "healthy": online, "detail": "online" if online else "offline"}
    except Exception as e:
        return {"name": "internet", "healthy": False, "detail": str(e)}


def _check_resources() -> Dict:
    try:
        snapshot = get_resource_monitor().snapshot()
        if "error" in snapshot:
            return {"name": "resources", "healthy": False, "detail": snapshot["error"]}

        problems = []
        if snapshot["cpu_percent"] >= CPU_WARNING_PERCENT:
            problems.append(f"CPU at {snapshot['cpu_percent']}%")
        if snapshot["memory_percent"] >= MEMORY_WARNING_PERCENT:
            problems.append(f"memory at {snapshot['memory_percent']}%")
        if snapshot["disk_percent"] >= DISK_WARNING_PERCENT:
            problems.append(f"disk at {snapshot['disk_percent']}%")

        return {
            "name": "resources",
            "healthy": not problems,
            "detail": "; ".join(problems) if problems else "normal",
            "snapshot": snapshot,
        }
    except Exception as e:
        return {"name": "resources", "healthy": False, "detail": str(e)}


def _check_storage_writable() -> Dict:
    """Confirm storage/ actually exists and is writable - a full disk or a
    permissions problem here breaks every SQLite-backed memory module silently."""
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        probe_file = STORAGE_DIR / ".health_check_probe"
        probe_file.write_text(str(time.time()))
        probe_file.unlink()

        free_gb = shutil.disk_usage(STORAGE_DIR).free / (1024**3)
        healthy = free_gb >= MIN_FREE_DISK_GB
        return {
            "name": "storage",
            "healthy": healthy,
            "detail": f"{round(free_gb, 2)} GB free" if healthy else f"low disk space: {round(free_gb, 2)} GB free",
        }
    except Exception as e:
        return {"name": "storage", "healthy": False, "detail": str(e)}


_DEFAULT_CHECKS: List[Callable[[], Dict]] = [_check_internet, _check_resources, _check_storage_writable]


def run_health_check(checks: List[Callable[[], Dict]] = None) -> Dict:
    """Run every registered check and return overall + per-check status.
    Pass a custom `checks` list to run a subset, or add project-specific
    checks (e.g. a plugin's own connectivity check) without editing this file."""
    checks = checks if checks is not None else _DEFAULT_CHECKS
    results = [check() for check in checks]
    overall_healthy = all(r.get("healthy") for r in results)

    return {
        "healthy": overall_healthy,
        "checked_at": time.time(),
        "checks": results,
    }


def get_health_status() -> Dict:
    """Alias for run_health_check() with the default check list. Was
    missing before, which meant ui/bridge.py's `from
    monitoring.health_check import get_health_status` silently failed
    every time and the UI's health widget always showed unavailable."""
    return run_health_check()
