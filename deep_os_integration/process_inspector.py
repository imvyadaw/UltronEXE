"""
process_inspector.py
=====================
Lists, inspects and manages running processes: CPU/RAM usage, open
files, start time, and the ability to (gracefully or forcefully) stop
a process ULTRON was asked to close.

Dependencies: pip install psutil
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional

import psutil

logger = logging.getLogger("ultron.process_inspector")


@dataclass
class ProcessInfo:
    pid: int
    name: str
    exe: Optional[str]
    status: str
    cpu_percent: float
    memory_mb: float
    num_threads: int
    created: str
    username: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class ProcessInspector:
    """Thin, safe wrapper around psutil for querying and managing processes."""

    def list_processes(self, sort_by: str = "memory_mb", top_n: Optional[int] = None) -> List[ProcessInfo]:
        procs = []
        for p in psutil.process_iter(["pid", "name", "exe", "status", "create_time", "username"]):
            try:
                with p.oneshot():
                    mem = p.memory_info().rss / (1024 * 1024)
                    procs.append(
                        ProcessInfo(
                            pid=p.pid,
                            name=p.info.get("name") or "",
                            exe=p.info.get("exe"),
                            status=p.info.get("status") or "",
                            cpu_percent=p.cpu_percent(interval=None),
                            memory_mb=round(mem, 1),
                            num_threads=p.num_threads(),
                            created=datetime.fromtimestamp(p.info["create_time"]).isoformat(timespec="seconds"),
                            username=p.info.get("username"),
                        )
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        procs.sort(key=lambda x: getattr(x, sort_by), reverse=True)
        return procs[:top_n] if top_n else procs

    def find_by_name(self, name: str) -> List[ProcessInfo]:
        name_lower = name.lower()
        return [p for p in self.list_processes() if name_lower in p.name.lower()]

    def get_info(self, pid: int) -> Optional[ProcessInfo]:
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                return ProcessInfo(
                    pid=p.pid,
                    name=p.name(),
                    exe=p.exe() if p.exe() else None,
                    status=p.status(),
                    cpu_percent=p.cpu_percent(interval=0.1),
                    memory_mb=round(p.memory_info().rss / (1024 * 1024), 1),
                    num_threads=p.num_threads(),
                    created=datetime.fromtimestamp(p.create_time()).isoformat(timespec="seconds"),
                    username=p.username(),
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def close_gracefully(self, pid: int, timeout: float = 5.0) -> bool:
        """Ask a process to terminate, escalate to kill only after timeout."""
        try:
            p = psutil.Process(pid)
            p.terminate()
            p.wait(timeout=timeout)
            logger.info("Process %s (%s) terminated gracefully", pid, p.name())
            return True
        except psutil.TimeoutExpired:
            try:
                p.kill()
                logger.warning("Process %s did not exit in time, force-killed", pid)
                return True
            except psutil.NoSuchProcess:
                return True
        except psutil.NoSuchProcess:
            return True
        except psutil.AccessDenied:
            logger.error("Access denied closing pid %s - try running as admin", pid)
            return False

    def system_snapshot(self) -> dict:
        """Overall CPU / memory / disk snapshot, useful for a quick status report."""
        vm = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.2),
            "cpu_per_core": psutil.cpu_percent(interval=0.2, percpu=True),
            "memory_percent": vm.percent,
            "memory_used_gb": round(vm.used / (1024**3), 2),
            "memory_total_gb": round(vm.total / (1024**3), 2),
            "process_count": len(psutil.pids()),
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(timespec="seconds"),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    inspector = ProcessInspector()
    print(inspector.system_snapshot())
    for proc in inspector.list_processes(top_n=5):
        print(proc.to_dict())
