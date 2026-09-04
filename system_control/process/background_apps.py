"""Background / Running Apps
============================
Monitor and control currently-running processes: list them (sorted by
CPU or memory), inspect one, find by name, and end one - the "Task
Manager > Processes tab" surface, complementing startup_manager.py
(what launches) and task_scheduler.py (what runs on a schedule).

Reading uses `psutil` when available (richer/faster, cross-platform)
and falls back to PowerShell's Get-Process on Windows if psutil isn't
installed - same fallback shape as HAS_<DEP> guards elsewhere in this
codebase. kill_process is confirm-gated and additionally refuses
outright (not just confirm-gated) to touch a short list of processes
that are critical to the OS or to ULTRON's own session staying alive,
mirroring device_manager.py's "don't let the model lock itself out"
caution for disabling devices.
"""

import subprocess
from typing import Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Processes ULTRON will never kill, confirm or not - ending these can
# crash or lock up the whole session (or ULTRON's own ability to run).
_PROTECTED_PROCESS_NAMES = {
    "system",
    "system idle process",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "lsm.exe",
    "explorer.exe",
    "svchost.exe",
    "dwm.exe",
    "python.exe",
    "pythonw.exe",
}


class BackgroundApps:
    """List/inspect/find/kill running processes; protects core OS processes."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found and psutil is not installed - " "install psutil or run on Windows."}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_running_processes(self, sort_by: str = "memory", top_n: int = 20) -> Dict:
        """List running processes, sorted by 'memory' or 'cpu', top_n rows."""
        if sort_by not in ("memory", "cpu"):
            return {"error": "sort_by must be 'memory' or 'cpu'"}
        top_n = max(1, min(int(top_n or 20), 200))

        if HAS_PSUTIL:
            try:
                procs = []
                for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
                    try:
                        info = p.info
                        procs.append(
                            {
                                "pid": info["pid"],
                                "name": info["name"],
                                "cpu_percent": info.get("cpu_percent") or 0.0,
                                "memory_mb": (
                                    round((info["memory_info"].rss / (1024 * 1024)), 2)
                                    if info.get("memory_info")
                                    else 0.0
                                ),
                            }
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                key = "memory_mb" if sort_by == "memory" else "cpu_percent"
                procs.sort(key=lambda x: x[key], reverse=True)
                return {"success": True, "processes": procs[:top_n], "count": len(procs)}
            except Exception as e:
                return {"error": str(e)}

        sort_prop = "WS" if sort_by == "memory" else "CPU"
        cmd = (
            f"Get-Process | Sort-Object -Property {sort_prop} -Descending | Select-Object -First {top_n} "
            f"Id,ProcessName,CPU,@{{Name='MemoryMB';Expression={{[math]::Round($_.WS/1MB,2)}}}} | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-Process failed"}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            procs = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "processes": procs, "count": len(procs)}

    def get_process_details(self, pid: int) -> Dict:
        """Full detail for one process by PID."""
        if HAS_PSUTIL:
            try:
                p = psutil.Process(int(pid))
                with p.oneshot():
                    return {
                        "success": True,
                        "pid": p.pid,
                        "name": p.name(),
                        "status": p.status(),
                        "cpu_percent": p.cpu_percent(interval=0.1),
                        "memory_mb": round(p.memory_info().rss / (1024 * 1024), 2),
                        "num_threads": p.num_threads(),
                        "create_time": p.create_time(),
                        "exe": self._safe(lambda: p.exe()),
                        "cmdline": self._safe(lambda: p.cmdline()),
                    }
            except psutil.NoSuchProcess:
                return {"error": f"No process with PID {pid}"}
            except psutil.AccessDenied:
                return {"error": f"Access denied reading process {pid} (try running ULTRON as Administrator)"}
            except Exception as e:
                return {"error": str(e)}

        cmd = f"Get-Process -Id {int(pid)} | Select-Object Id,ProcessName,Path,StartTime,CPU,WS | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"No process with PID {pid}"}
        import json

        try:
            info = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "process": info}

    def _safe(self, fn):
        try:
            return fn()
        except Exception:
            return None

    def find_process(self, name: str) -> Dict:
        """Find running processes whose name contains the given (case-insensitive) string."""
        if not name:
            return {"error": "name must be non-empty"}
        query = name.lower()
        if HAS_PSUTIL:
            try:
                matches = []
                for p in psutil.process_iter(["pid", "name"]):
                    try:
                        if query in (p.info["name"] or "").lower():
                            matches.append({"pid": p.info["pid"], "name": p.info["name"]})
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
                return {"success": True, "matches": matches, "count": len(matches)}
            except Exception as e:
                return {"error": str(e)}

        safe_name = name.replace("'", "''")
        cmd = f"Get-Process | Where-Object {{$_.ProcessName -like '*{safe_name}*'}} | Select-Object Id,ProcessName | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-Process failed"}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            matches = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "matches": matches, "count": len(matches)}

    def kill_process(self, pid: int, confirm: bool = False) -> Dict:
        """End a running process by PID. Refuses outright (no confirm can
        override this) for a short list of processes critical to the OS
        or to ULTRON's own session. Otherwise confirm-gated."""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return {"error": "pid must be an integer"}

        name = self._get_name_for_pid(pid)
        if name and name.strip().lower() in _PROTECTED_PROCESS_NAMES:
            return {
                "error": f"Refusing to kill {name!r} (PID {pid}) - this process is critical "
                "to the OS or to ULTRON's own session and is never allowed to be killed."
            }

        if not confirm:
            label = f"{name!r} (PID {pid})" if name else f"PID {pid}"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would end process {label}",
                "message": "Call again with confirm=true to apply.",
            }

        if HAS_PSUTIL:
            try:
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=5)
                except psutil.TimeoutExpired:
                    p.kill()
                return {"success": True, "pid": pid, "name": name}
            except psutil.NoSuchProcess:
                return {"error": f"No process with PID {pid}"}
            except psutil.AccessDenied:
                return {"error": f"Access denied ending process {pid} (try running ULTRON as Administrator)"}
            except Exception as e:
                return {"error": str(e)}

        try:
            result = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or result.stdout.strip() or "taskkill failed"}
            return {"success": True, "pid": pid, "name": name}
        except FileNotFoundError:
            return {"error": "taskkill not found - this is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def _get_name_for_pid(self, pid: int):
        if HAS_PSUTIL:
            try:
                return psutil.Process(pid).name()
            except Exception:
                return None
        result = self._run_ps(f"(Get-Process -Id {pid}).ProcessName")
        if result.get("success"):
            return result.get("stdout") or None
        return None
