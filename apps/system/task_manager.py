"""Windows Task Manager automation (plus direct psutil process control,
which is more reliable than driving the Task Manager GUI)."""

from typing import Dict, List

from apps.base_app import BaseApp

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class TaskManagerApp(BaseApp):
    """Open Task Manager, list processes, and end tasks."""

    APP_NAME = "task manager"
    PROCESS_NAMES = ["taskmgr.exe", "taskmgr"]
    EXE_HINTS = ["taskmgr", "taskmgr.exe"]

    def list_processes(self, sort_by_memory: bool = True) -> Dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            procs: List[Dict] = []
            for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
                mem = p.info.get("memory_info")
                procs.append(
                    {
                        "pid": p.info["pid"],
                        "name": p.info.get("name"),
                        "memory_mb": round(mem.rss / (1024 * 1024), 1) if mem else 0,
                        "cpu_percent": p.info.get("cpu_percent", 0.0),
                    }
                )
            if sort_by_memory:
                procs.sort(key=lambda x: x["memory_mb"], reverse=True)
            return {"success": True, "count": len(procs), "processes": procs[:50]}
        except Exception as e:
            return {"error": str(e)}

    def end_task(self, name_or_pid) -> Dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            killed = []
            for p in psutil.process_iter(["pid", "name"]):
                if (
                    str(p.info["pid"]) == str(name_or_pid)
                    or (p.info.get("name") or "").lower() == str(name_or_pid).lower()
                ):
                    p.terminate()
                    killed.append(p.info)
            if killed:
                return {"success": True, "killed": killed}
            return {"success": False, "error": f"No process matching '{name_or_pid}' found"}
        except Exception as e:
            return {"error": str(e)}
