"""Process management
===================
List, inspect, and kill running processes by name or PID. Uses psutil
(already a project dependency for battery/CPU/RAM status).

Renamed from process/process.py (ProcessTools) as part of Phase 8's
windows/ restructure - process/manager.py / ProcessManager to match
the naming used by every other domain subpackage (apps/, registry/,
etc). Only windows/__init__.py imported the old module, so this is a
clean rename with no other call sites to update.
"""

from typing import Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _admin_aware_error(base_error: str) -> str:
    """Same reasoning as windows/firewall/rules.py's helper of the same
    name - a psutil.AccessDenied here almost always means the target
    process belongs to another user/session or is a protected system
    process, both of which need admin rights to touch."""
    try:
        from windows.system_info.admin import is_admin, permission_denied_hint

        if not is_admin():
            return base_error + permission_denied_hint("Killing this process")
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("windows.process.manager._admin_aware_error")
    return base_error


class ProcessManager:
    """List/inspect/kill OS processes."""

    def list_processes(self, sort_by: str = "memory", limit: int = 30) -> Dict:
        """List running processes, sorted by 'memory' or 'cpu' usage."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            procs = []
            for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
                try:
                    info = p.info
                    procs.append(
                        {
                            "pid": info["pid"],
                            "name": info["name"],
                            "memory_percent": round(info.get("memory_percent") or 0, 2),
                            "cpu_percent": info.get("cpu_percent") or 0,
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
            procs.sort(key=lambda x: x[key], reverse=True)
            return {"count": len(procs), "processes": procs[:limit]}
        except Exception as e:
            return {"error": str(e)}

    def find_process(self, name: str) -> Dict:
        """Find running process(es) matching a name (case-insensitive, partial match)."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            matches = []
            name_lower = name.lower()
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if name_lower in (p.info["name"] or "").lower():
                        matches.append({"pid": p.info["pid"], "name": p.info["name"]})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return {"query": name, "count": len(matches), "matches": matches}
        except Exception as e:
            return {"error": str(e)}

    def kill_process(self, name: str = None, pid: int = None, force: bool = False, confirm: bool = False) -> Dict:
        """Kill a process by name or PID. Safety-gated: needs confirm=true. Kills all matches if multiple share a name."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        if not name and not pid:
            return {"error": "Provide either a process name or a PID"}
        if not confirm:
            return {"error": f"This will kill process {name or pid}. Call again with confirm=true to proceed."}
        try:
            killed = []
            denied = []
            if pid:
                targets = [psutil.Process(pid)]
            else:
                name_lower = name.lower()
                targets = [
                    p for p in psutil.process_iter(["pid", "name"]) if name_lower in (p.info["name"] or "").lower()
                ]
            if not targets:
                return {"error": f"No running process matched: {name or pid}"}
            for p in targets:
                try:
                    if force:
                        p.kill()
                    else:
                        p.terminate()
                    killed.append({"pid": p.pid, "name": p.name()})
                except psutil.NoSuchProcess:
                    continue
                except psutil.AccessDenied:
                    # Bug fix: this used to be silently skipped, so a
                    # kill that failed purely on permissions still came
                    # back as {"success": True, "count": 0} with no
                    # indication anything was wrong - exactly the kind
                    # of failure that looks like Ultron is broken
                    # rather than just not elevated.
                    denied.append({"pid": p.pid, "name": p.name() if p.is_running() else name})
                    continue
            if not killed and denied:
                return {
                    "error": _admin_aware_error(
                        f"Access denied killing {len(denied)} matching process(es): " f"{[d['name'] for d in denied]}"
                    )
                }
            result = {"success": True, "killed": killed, "count": len(killed)}
            if denied:
                result["access_denied"] = denied
                result["note"] = _admin_aware_error(f"{len(denied)} other matching process(es) could not be killed")
            return result
        except psutil.NoSuchProcess:
            return {"error": f"No process with PID {pid}"}
        except Exception as e:
            return {"error": str(e)}

    def get_process_info(self, pid: int) -> Dict:
        """Get detailed info about a single process by PID."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                return {
                    "pid": p.pid,
                    "name": p.name(),
                    "status": p.status(),
                    "cpu_percent": p.cpu_percent(interval=0.2),
                    "memory_mb": round(p.memory_info().rss / (1024 * 1024), 1),
                    "created": p.create_time(),
                    "num_threads": p.num_threads(),
                }
        except psutil.NoSuchProcess:
            return {"error": f"No process with PID {pid}"}
        except Exception as e:
            return {"error": str(e)}

    def set_priority(self, pid: int, priority: str) -> Dict:
        """Set process priority: 'low', 'below_normal', 'normal', 'above_normal', 'high', 'realtime'."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        priority_map = {
            "low": psutil.IDLE_PRIORITY_CLASS if hasattr(psutil, "IDLE_PRIORITY_CLASS") else None,
            "below_normal": getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", None),
            "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", None),
            "above_normal": getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", None),
            "high": getattr(psutil, "HIGH_PRIORITY_CLASS", None),
            "realtime": getattr(psutil, "REALTIME_PRIORITY_CLASS", None),
        }
        level = priority_map.get(priority.lower())
        if level is None:
            return {"error": f"Unknown priority '{priority}'. Options: {list(priority_map)}"}
        try:
            p = psutil.Process(pid)
            p.nice(level)
            return {"success": True, "pid": pid, "priority": priority}
        except psutil.NoSuchProcess:
            return {"error": f"No process with PID {pid}"}
        except Exception as e:
            return {"error": str(e)}
