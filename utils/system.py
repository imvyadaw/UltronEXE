"""
utils/system.py - lightweight, stdlib-only platform info (which OS,
which Python, how much free disk space). For live CPU/RAM/disk
*monitoring* with history and alerting, use
monitoring/resource_monitor.py instead - that one depends on psutil
and is meant to be polled repeatedly; this one is a cheap one-shot
check any script or skill can call without pulling in psutil.
"""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_linux() -> bool:
    return platform.system() == "Linux"


def is_macos() -> bool:
    return platform.system() == "Darwin"


def disk_usage(path: Optional[str] = None) -> Dict[str, int]:
    """Total/used/free bytes for the filesystem containing `path`
    (defaults to the project root's drive).

    >>> usage = disk_usage(".")
    >>> usage["total"] >= usage["used"] >= 0
    True
    """
    target = path or str(Path(__file__).resolve().parents[1])
    total, used, free = shutil.disk_usage(target)
    return {"total": total, "used": used, "free": free}


def system_info() -> Dict[str, str]:
    """One-shot snapshot of OS/Python identity - useful in bug reports,
    `scripts/setup.py` diagnostics, or any "what am I running on" log line.

    >>> info = system_info()
    >>> "python_version" in info
    True
    """
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "executable": sys.executable,
    }
