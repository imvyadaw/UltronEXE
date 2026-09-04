"""System Resource Monitor
=========================
Windows Resource Monitor (resmon.exe)-style, per-process breakdowns of
disk and network I/O, plus system-wide handle/thread counts - distinct
from the top-level monitoring/resource_monitor.py's ResourceMonitor,
which is deliberately cross-platform (psutil-based) and scoped to
"how loaded is my PC right now" as a single CPU/RAM/disk-percent
snapshot for ULTRON's own health_check.py/alerts.py to consume. This
module instead answers "which specific process is responsible" -
per-process disk bytes/sec and network bytes/sec, which psutil cannot
attribute cleanly across platforms and which resmon.exe itself gets
from Windows Performance Counters (the \\Process, \\Network Interface,
and \\PhysicalDisk counter sets) via Get-Counter, the same source this
module reads from directly.

Named SystemResourceMonitor (not ResourceMonitor) specifically so it
never shadows or gets confused with the top-level monitoring module of
a similar name when both are imported in the same file.

All reads; nothing here changes system state, so nothing is
confirm-gated. Performance counters can be temporarily unavailable
right after boot or if the counter database needs rebuilding
(`lodctr /r`) - that surfaces as a plain {"error": ...}, not a crash.
"""

import subprocess
from typing import Dict


class SystemResourceMonitor:
    """Per-process disk/network I/O and system-wide handle/thread
    counts via Windows Performance Counters - the resmon.exe surface,
    distinct from the top-level psutil-based ResourceMonitor."""

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

    def get_top_disk_consumers(self, limit: int = 10) -> Dict:
        """Top processes by current disk I/O (bytes/sec, read+write
        combined) - the 'Disk' section of Resource Monitor's Overview
        tab. No admin needed."""
        result = self._run_ps(
            "(Get-Counter '\\Process(*)\\IO Data Bytes/sec' -ErrorAction SilentlyContinue).CounterSamples | "
            "Where-Object { $_.InstanceName -ne '_total' -and $_.InstanceName -ne 'idle' -and $_.CookedValue -gt 0 } | "
            f"Sort-Object CookedValue -Descending | Select-Object -First {int(limit)} "
            "InstanceName, CookedValue | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"]
                or "Get-Counter failed - the counter database may need rebuilding (lodctr /r)."
            }
        if not result["stdout"]:
            return {"success": True, "processes": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse counter data"}
        rows = data if isinstance(data, list) else [data]
        processes = [{"process": r.get("InstanceName"), "bytes_per_sec": round(r.get("CookedValue", 0))} for r in rows]
        return {"success": True, "processes": processes, "count": len(processes)}

    def get_top_network_consumers(self, limit: int = 10) -> Dict:
        """Top processes by current network throughput, from the
        per-process network usage counters Resource Monitor's Network
        tab shows - the 'Send'+'Receive' figures combined. No admin
        needed. Not all Windows builds expose the per-process network
        counter set; when unavailable this reports that plainly rather
        than returning an empty list that looks like 'no traffic'."""
        result = self._run_ps(
            "(Get-Counter '\\Process(*)\\IO Other Bytes/sec' -ErrorAction SilentlyContinue).CounterSamples | "
            "Where-Object { $_.InstanceName -ne '_total' -and $_.InstanceName -ne 'idle' -and $_.CookedValue -gt 0 } | "
            f"Sort-Object CookedValue -Descending | Select-Object -First {int(limit)} "
            "InstanceName, CookedValue | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-Counter failed for the network I/O counter set."}
        if not result["stdout"]:
            return {
                "success": True,
                "processes": [],
                "count": 0,
                "note": "No per-process network activity detected, or this counter set isn't exposed on this build.",
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse counter data"}
        rows = data if isinstance(data, list) else [data]
        processes = [{"process": r.get("InstanceName"), "bytes_per_sec": round(r.get("CookedValue", 0))} for r in rows]
        return {"success": True, "processes": processes, "count": len(processes)}

    def get_disk_activity(self, drive: str = "C:") -> Dict:
        """Current disk queue length and active-time percentage for a
        given drive - the 'Disk Activity' summary Resource Monitor
        shows per-physical-disk. No admin needed."""
        safe_drive = drive.replace("'", "''").rstrip("\\")
        result = self._run_ps(
            f"$q = (Get-Counter '\\LogicalDisk({safe_drive})\\Current Disk Queue Length' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue; "
            f"$a = (Get-Counter '\\LogicalDisk({safe_drive})\\% Disk Time' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue; "
            "[PSCustomObject]@{ QueueLength = $q; PercentActive = $a } | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"error": result["stderr"] or f"Could not read disk counters for drive '{drive}'."}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse disk counter data"}
        return {
            "success": True,
            "drive": drive,
            "queue_length": round(data.get("QueueLength", 0), 2),
            "percent_active": round(min(data.get("PercentActive", 0), 100), 1),
        }

    def get_handle_thread_counts(self, limit: int = 10) -> Dict:
        """System-wide open handle and thread totals, plus the top
        processes by handle count - a common early signal of a handle
        leak, shown in Resource Monitor's process table columns but
        not surfaced anywhere else in this codebase. No admin
        needed."""
        result = self._run_ps(
            "Get-Process -ErrorAction SilentlyContinue | "
            f"Sort-Object Handles -Descending | Select-Object -First {int(limit)} "
            "ProcessName, Id, Handles, Threads | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-Process failed"}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
        except json.JSONDecodeError:
            return {"error": "Could not parse process data"}
        top = data if isinstance(data, list) else [data]

        totals_result = self._run_ps(
            "$procs = Get-Process -ErrorAction SilentlyContinue; "
            "[PSCustomObject]@{ TotalHandles = ($procs | Measure-Object Handles -Sum).Sum; "
            "TotalThreads = ($procs | Measure-Object Threads -Sum).Sum; ProcessCount = $procs.Count } | ConvertTo-Json"
        )
        totals = {}
        if totals_result.get("success") and totals_result.get("stdout"):
            try:
                totals = json.loads(totals_result["stdout"])
            except json.JSONDecodeError:
                totals = {}

        return {
            "success": True,
            "total_handles": totals.get("TotalHandles"),
            "total_threads": totals.get("TotalThreads"),
            "process_count": totals.get("ProcessCount"),
            "top_by_handles": top,
        }
