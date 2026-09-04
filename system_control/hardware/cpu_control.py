"""CPU Control
=============
CPU *hardware and power-state* control - distinct from
system_control/process/background_apps.py, which already owns
listing/sorting/killing running processes by CPU usage. This module's
process-level surface is limited to what that one doesn't cover:
per-process priority and core affinity. Everything else here is about
the chip itself - identity/specs, live utilization, and the min/max
processor-state throttle that governs how hard it's allowed to run.

Reads use WMI (`Win32_Processor`) for static info and `psutil` (when
available) for live utilization, same HAS_<DEP> fallback shape used
elsewhere. Throttle range is read/set via `powercfg` against the
active scheme's PROCTHROTTLEMIN/MAX settings - the same mechanism
Windows' own "Processor power management" control panel uses, so a
change here shows up there too.

set_max_processor_state and set_process_priority/set_process_affinity
are confirm-gated: throttling the CPU can noticeably slow the whole
machine (including ULTRON itself) until reverted, and re-priming a
process's priority/affinity can starve it or the rest of the system
of scheduling time.
"""

import subprocess
from typing import Dict, List

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# powercfg GUIDs for the "Processor power management" subgroup and its
# min/max processor state settings - stable across Windows versions.
_SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
_PROCTHROTTLEMIN = "893dee8e-2bef-41e0-89c6-b55d0929964c"
_PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"

_PRIORITY_CLASSES = {
    "idle": "IDLE_PRIORITY_CLASS",
    "below_normal": "BELOW_NORMAL_PRIORITY_CLASS",
    "normal": "NORMAL_PRIORITY_CLASS",
    "above_normal": "ABOVE_NORMAL_PRIORITY_CLASS",
    "high": "HIGH_PRIORITY_CLASS",
    "realtime": "REALTIME_PRIORITY_CLASS",
}


class CPUControl:
    """CPU identity/specs, live utilization, processor-state throttle,
    and per-process priority/affinity."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_cpu_info(self) -> Dict:
        """Static CPU identity: name, cores/threads, base clock,
        socket, architecture. No admin needed."""
        result = self._run_ps(
            "Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, "
            "NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, SocketDesignation, "
            "Architecture, L2CacheSize, L3CacheSize | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"error": result["stderr"] or "Could not read CPU info"}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse CPU info"}
        if isinstance(data, list):
            data = data[0] if data else {}
        return {"success": True, "cpu": data}

    def get_cpu_usage(self, per_core: bool = False, interval_seconds: float = 0.5) -> Dict:
        """Live CPU utilization, overall or per logical core. Uses
        psutil when available; falls back to a one-shot WMI load
        percentage sample otherwise (less precise, no per-core split)."""
        if HAS_PSUTIL:
            if per_core:
                usage = psutil.cpu_percent(interval=interval_seconds, percpu=True)
                return {"success": True, "per_core_percent": usage, "core_count": len(usage)}
            usage = psutil.cpu_percent(interval=interval_seconds)
            return {"success": True, "overall_percent": usage}
        result = self._run_ps("(Get-CimInstance Win32_Processor).LoadPercentage")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read CPU load"}
        try:
            return {"success": True, "overall_percent": float(result["stdout"].splitlines()[0])}
        except (ValueError, IndexError):
            return {"error": "Could not parse CPU load", "raw": result["stdout"]}

    def get_processor_throttle(self) -> Dict:
        """Current min/max processor-state percentages for the active
        power scheme (AC). No admin needed."""
        out = {}
        for key, guid in (("min_percent", _PROCTHROTTLEMIN), ("max_percent", _PROCTHROTTLEMAX)):
            result = self._run_ps(f"powercfg /getactvalueindex SCHEME_CURRENT {_SUB_PROCESSOR} {guid}")
            if "error" in result:
                return result
            if not result["success"]:
                return {"error": result["stderr"] or "powercfg query failed"}
            digits = "".join(c for c in result["stdout"] if c.isdigit())
            out[key] = int(digits) if digits else None
        return {"success": True, **out}

    def set_max_processor_state(self, percent: int, on_battery: bool = False, confirm: bool = False) -> Dict:
        """Cap how hard the CPU is allowed to run (thermal/battery/
        noise management) - the same slider as Control Panel's
        Processor power management > Maximum processor state.
        Confirm-gated: this throttles the whole machine, including
        ULTRON, until reverted (set back to 100)."""
        if not 1 <= percent <= 100:
            return {"error": "percent must be between 1 and 100"}
        scope = "battery (DC)" if on_battery else "plugged in (AC)"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will cap maximum CPU performance to {percent}% while {scope}, "
                f"slowing the whole system (including ULTRON) until reverted.",
            }
        flag = "/setdcvalueindex" if on_battery else "/setacvalueindex"
        result = self._run_ps(
            f"powercfg {flag} SCHEME_CURRENT {_SUB_PROCESSOR} {_PROCTHROTTLEMAX} {percent}; "
            f"powercfg /setactive SCHEME_CURRENT"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to set max processor state"}
        return {"success": True, "max_percent": percent, "on_battery": on_battery}

    def set_process_priority(self, pid: int, priority: str, confirm: bool = False) -> Dict:
        """Change a running process's scheduling priority (one of:
        idle, below_normal, normal, above_normal, high, realtime).
        Confirm-gated: 'realtime' in particular can starve the OS's
        own input/scheduling and make the machine feel unresponsive."""
        cls = _PRIORITY_CLASSES.get(priority.lower())
        if not cls:
            return {"error": f"Unknown priority '{priority}'. Use one of: {sorted(_PRIORITY_CLASSES)}"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set process {pid}'s priority to '{priority}'"
                + (" - can make the whole system feel unresponsive." if priority.lower() == "realtime" else "."),
            }
        if HAS_PSUTIL:
            try:
                proc = psutil.Process(pid)
                proc.nice(
                    {
                        "idle": psutil.IDLE_PRIORITY_CLASS,
                        "below_normal": psutil.BELOW_NORMAL_PRIORITY_CLASS,
                        "normal": psutil.NORMAL_PRIORITY_CLASS,
                        "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                        "high": psutil.HIGH_PRIORITY_CLASS,
                        "realtime": psutil.REALTIME_PRIORITY_CLASS,
                    }[priority.lower()]
                )
                return {"success": True, "pid": pid, "priority": priority}
            except psutil.NoSuchProcess:
                return {"error": f"No process with pid {pid}"}
            except psutil.AccessDenied:
                return {"error": f"Access denied changing priority of pid {pid} - try running ULTRON as Administrator."}
            except Exception as e:
                return {"error": str(e)}
        result = self._run_ps(f"(Get-Process -Id {pid}).PriorityClass = '{cls}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Could not set priority for pid {pid}"}
        return {"success": True, "pid": pid, "priority": priority}

    def set_process_affinity(self, pid: int, cpu_indices: List[int], confirm: bool = False) -> Dict:
        """Restrict a process to a specific set of logical CPU cores
        (e.g. [0, 1] pins it to the first two cores). Confirm-gated -
        an overly narrow mask can badly slow the target process."""
        if not cpu_indices:
            return {"error": "cpu_indices must be non-empty"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will restrict process {pid} to CPU cores {cpu_indices}.",
            }
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil (required for affinity control)"}
        try:
            proc = psutil.Process(pid)
            proc.cpu_affinity(cpu_indices)
            return {"success": True, "pid": pid, "cpu_affinity": cpu_indices}
        except psutil.NoSuchProcess:
            return {"error": f"No process with pid {pid}"}
        except psutil.AccessDenied:
            return {"error": f"Access denied changing affinity of pid {pid} - try running ULTRON as Administrator."}
        except ValueError as e:
            return {"error": f"Invalid CPU index: {e}"}
        except Exception as e:
            return {"error": str(e)}
