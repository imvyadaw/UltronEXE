"""RAM Optimizer
===============
RAM *hardware info and memory-pressure relief* - distinct from
system_control/process/background_apps.py (already owns "list/sort
processes by memory usage"; not duplicated here). This module covers
what that one doesn't: installed-module inventory (slots/capacity/
speed), system-wide memory pressure, and the handful of well-known
techniques for relieving it - trimming a process's working set and
clearing the standby (cached) list.

Live totals use `ctypes.windll.kernel32.GlobalMemoryStatusEx` (no
subprocess needed, always available on Windows); physical-module
detail (slots, per-stick size/speed) comes from WMI `Win32_
PhysicalMemory` since GlobalMemoryStatusEx doesn't expose per-slot
data. trim_process_working_set is a courtesy hint to the OS
(`SetProcessWorkingSetSize(-1,-1)`), not a hard guarantee - Windows
may reclaim the pages right back if the process is still using them
heavily. clear_standby_list needs the third-party `EmptyStandbyList.
exe` (Sysinternals-style tool, not part of Windows) since there is no
supported first-party API for it; if it isn't present on PATH the
method says so rather than silently no-op'ing. Both memory-relief
methods are confirm-gated: trimming can cause brief re-paging
slowdowns, and clearing standby memory discards data Windows was
caching for performance (it will simply be re-read from disk next
time, but that first re-read after clearing will be slower).
"""
import logging

import ctypes
import shutil
import subprocess
from typing import Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class RAMOptimizer:
    """RAM hardware inventory, live memory pressure, and memory-relief actions."""

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

    def get_memory_status(self) -> Dict:
        """Live totals: total/available physical RAM, page file, and
        current memory-load percentage. No admin needed."""
        try:
            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return {"error": "GlobalMemoryStatusEx failed"}
            gb = 1024**3
            return {
                "success": True,
                "memory_load_percent": stat.dwMemoryLoad,
                "total_physical_gb": round(stat.ullTotalPhys / gb, 2),
                "available_physical_gb": round(stat.ullAvailPhys / gb, 2),
                "total_pagefile_gb": round(stat.ullTotalPageFile / gb, 2),
                "available_pagefile_gb": round(stat.ullAvailPageFile / gb, 2),
            }
        except AttributeError:
            return {"error": "GlobalMemoryStatusEx not available - this is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def get_physical_memory_info(self) -> Dict:
        """Per-slot RAM module detail: capacity, speed, manufacturer,
        form factor. No admin needed."""
        result = self._run_ps(
            "Get-CimInstance Win32_PhysicalMemory | Select-Object BankLabel, DeviceLocator, "
            "Capacity, Speed, Manufacturer, PartNumber, MemoryType | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read physical memory info"}
        if not result["stdout"]:
            return {"modules": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse memory module info"}
        modules = data if isinstance(data, list) else [data]
        for m in modules:
            cap = m.get("Capacity")
            if cap:
                try:
                    m["capacity_gb"] = round(int(cap) / (1024**3), 2)
                except (TypeError, ValueError):
                    logging.getLogger(__name__).exception("Suppressed (TypeError, ValueError)")
        return {"success": True, "modules": modules, "count": len(modules)}

    def get_top_memory_consumers(self, limit: int = 10) -> Dict:
        """Top processes by working-set memory, for deciding what to
        trim/close. Thin convenience wrapper; process listing/killing
        itself lives in system_control/process/background_apps.py."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                mem = p.info["memory_info"]
                if mem:
                    procs.append(
                        {"pid": p.info["pid"], "name": p.info["name"], "memory_mb": round(mem.rss / (1024**2), 1)}
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x["memory_mb"], reverse=True)
        return {"success": True, "processes": procs[:limit]}

    def trim_process_working_set(self, pid: int, confirm: bool = False) -> Dict:
        """Ask Windows to trim a process's working set back to the OS
        (SetProcessWorkingSetSize(-1,-1)) - a courtesy hint, not a
        guarantee; the process can grow right back if it's actively
        using that memory. Confirm-gated: can cause a brief re-paging
        slowdown for that process immediately after."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will trim process {pid}'s working set, possibly causing a brief slowdown as it re-pages memory back in.",
            }
        try:
            PROCESS_SET_QUOTA = 0x0100
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_QUERY_INFORMATION, False, pid)
            if not handle:
                return {"error": f"Could not open process {pid} - it may not exist, or needs Administrator."}
            try:
                ok = ctypes.windll.kernel32.SetProcessWorkingSetSize(handle, ctypes.c_size_t(-1), ctypes.c_size_t(-1))
                if not ok:
                    return {"error": f"SetProcessWorkingSetSize failed for pid {pid} (error {ctypes.GetLastError()})"}
                return {"success": True, "pid": pid, "trimmed": True}
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except AttributeError:
            return {"error": "Working-set trim is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def clear_standby_list(self, confirm: bool = False) -> Dict:
        """Clear the standby (cached-but-reclaimable) memory list,
        freeing 'available' RAM at the cost of Windows having to
        re-read that cached data from disk next time it's needed.
        Requires the third-party EmptyStandbyList.exe on PATH (no
        first-party Windows API for this exists) and admin rights.
        Confirm-gated."""
        exe = shutil.which("EmptyStandbyList") or shutil.which("EmptyStandbyList.exe")
        if not exe:
            return {
                "error": "EmptyStandbyList.exe not found on PATH. This isn't a built-in Windows tool - "
                "download it (e.g. from Wj32/CleanMem tooling) and place it on PATH to enable this action."
            }
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will clear the standby memory list, freeing cached RAM - the first disk read "
                "of anything that was cached will be slower afterward. Needs Administrator.",
            }
        try:
            result = subprocess.run([exe, "workingsets"], capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip() or "EmptyStandbyList failed"
                if "access" in err.lower() or "denied" in err.lower():
                    err += " - run ULTRON as Administrator."
                return {"error": err}
            return {"success": True, "cleared": True}
        except subprocess.TimeoutExpired:
            return {"error": "EmptyStandbyList timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_pagefile_config(self) -> Dict:
        """Current page file settings (path, initial/max size, or
        system-managed). No admin needed."""
        result = self._run_ps(
            "Get-CimInstance Win32_PageFileSetting | Select-Object Name, InitialSize, MaximumSize | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read page file settings"}
        if not result["stdout"]:
            return {"success": True, "system_managed": True, "settings": []}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse page file settings"}
        return {"success": True, "system_managed": False, "settings": data if isinstance(data, list) else [data]}

    def set_pagefile_size(self, drive: str, initial_mb: int, maximum_mb: int, confirm: bool = False) -> Dict:
        """Set a custom (non system-managed) page file size on the
        given drive (e.g. 'C:'). Confirm-gated and needs admin -
        undersizing this can cause out-of-memory failures under load,
        and applying it requires a reboot to fully take effect."""
        if initial_mb <= 0 or maximum_mb <= 0 or maximum_mb < initial_mb:
            return {"error": "initial_mb and maximum_mb must be positive, with maximum_mb >= initial_mb"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set the page file on {drive} to initial={initial_mb}MB / max={maximum_mb}MB "
                f"(takes full effect after reboot). Needs Administrator.",
            }
        safe_drive = drive.rstrip("\\").replace("'", "''")
        script = (
            f"$cs = Get-CimInstance Win32_ComputerSystem; "
            f"if ($cs.AutomaticManagedPagefile) {{ Set-CimInstance -InputObject $cs -Property @{{AutomaticManagedPagefile=$false}} }}; "
            f"$existing = Get-CimInstance Win32_PageFileSetting | Where-Object {{ $_.Name -like '{safe_drive}*' }}; "
            f"if ($existing) {{ Set-CimInstance -InputObject $existing -Property @{{InitialSize={initial_mb}; MaximumSize={maximum_mb}}} }} "
            f"else {{ New-CimInstance -ClassName Win32_PageFileSetting -Property @{{Name='{safe_drive}\\\\pagefile.sys'; InitialSize={initial_mb}; MaximumSize={maximum_mb}}} }}"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or "Failed to set page file size"
            if "access" in err.lower() or "denied" in err.lower():
                err += " - run ULTRON as Administrator."
            return {"error": err}
        return {
            "success": True,
            "drive": drive,
            "initial_mb": initial_mb,
            "maximum_mb": maximum_mb,
            "reboot_required": True,
        }
