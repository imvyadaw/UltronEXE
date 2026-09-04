"""Disk Health Monitor
======================
SMART/storage-reliability health via Windows' own Storage Management
stack (Get-PhysicalDisk / Get-StorageReliabilityCounter) - distinct
from storage/disk_quota.py (per-user quota limits, not health) and
from quantum_dashboard/predictive_maintenance.py's optional pySMART-
based reader (needs smartctl + admin). This module uses the built-in
Windows Storage Management API instead, so it works without any extra
install, at the cost of coarser data than raw SMART attributes (no
per-attribute raw/threshold/worst values - Windows exposes health
status, temperature, wear, and error counters directly instead).

All reads; nothing here changes system state, so nothing is
confirm-gated.
"""

import subprocess
from typing import Dict, Optional


class DiskHealthMonitor:
    """Physical-disk health status, reliability counters, and volume
    free-space via the built-in Windows Storage Management stack."""

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

    def get_physical_disks(self) -> Dict:
        """List physical disks with Windows' own rollup health status
        (Healthy/Warning/Unhealthy), media type (SSD/HDD), and size.
        No admin needed."""
        result = self._run_ps(
            "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
            "Select-Object DeviceId, FriendlyName, MediaType, HealthStatus, OperationalStatus, "
            "Size, BusType | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {
                "error": result["stderr"] or "Get-PhysicalDisk failed - Storage Management module may be unavailable."
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse disk data"}
        rows = data if isinstance(data, list) else [data]
        return {"success": True, "disks": rows, "count": len(rows)}

    def get_reliability_counters(self, disk_id: Optional[str] = None) -> Dict:
        """Per-disk reliability counters - temperature, power-on hours,
        wear percentage (SSD), and read/write/flush error totals - the
        closest built-in equivalent to raw SMART attributes. Needs
        admin on most systems."""
        filt = f"| Where-Object {{ $_.DeviceId -eq '{disk_id}' }}" if disk_id else ""
        result = self._run_ps(
            f"Get-PhysicalDisk {filt} -ErrorAction SilentlyContinue | Get-StorageReliabilityCounter "
            "-ErrorAction SilentlyContinue | Select-Object DeviceId, Temperature, TemperatureMax, "
            "Wear, PowerOnHours, ReadErrorsTotal, WriteErrorsTotal, ReadErrorsUncorrected, "
            "WriteErrorsUncorrected | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"]
                or "Get-StorageReliabilityCounter failed - this usually needs admin, "
                "and isn't supported by every disk/controller."
            }
        if not result["stdout"]:
            return {
                "success": True,
                "disks": [],
                "count": 0,
                "note": "No reliability counters reported for this hardware/controller.",
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse reliability counter data"}
        rows = data if isinstance(data, list) else [data]
        return {"success": True, "disks": rows, "count": len(rows)}

    def get_volume_space_summary(self) -> Dict:
        """Free/used space per volume/drive letter. No admin needed."""
        result = self._run_ps(
            "Get-Volume -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter } | "
            "Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus, "
            "SizeRemaining, Size | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"error": result["stderr"] or "Get-Volume failed"}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse volume data"}
        rows = data if isinstance(data, list) else [data]
        volumes = []
        for r in rows:
            size = r.get("Size") or 0
            remaining = r.get("SizeRemaining") or 0
            used_pct = round((1 - (remaining / size)) * 100, 1) if size else None
            volumes.append(
                {
                    "drive": r.get("DriveLetter"),
                    "label": r.get("FileSystemLabel"),
                    "file_system": r.get("FileSystem"),
                    "health_status": r.get("HealthStatus"),
                    "size_bytes": size,
                    "free_bytes": remaining,
                    "used_percent": used_pct,
                }
            )
        return {"success": True, "volumes": volumes, "count": len(volumes)}

    def check_health_alerts(self, wear_warn_percent: float = 80.0) -> Dict:
        """Roll up get_physical_disks() + get_reliability_counters()
        into a flat list of anything worth flagging: non-Healthy
        HealthStatus, SSD wear above threshold, or any uncorrected
        read/write errors. No admin needed for the disk list; the
        reliability-counter part degrades gracefully without admin."""
        disks = self.get_physical_disks()
        if "error" in disks:
            return disks
        alerts = []
        for d in disks.get("disks", []):
            if d.get("HealthStatus") and d["HealthStatus"] != "Healthy":
                alerts.append(
                    {
                        "device_id": d.get("DeviceId"),
                        "name": d.get("FriendlyName"),
                        "issue": f"HealthStatus is {d['HealthStatus']}",
                    }
                )

        counters = self.get_reliability_counters()
        if "error" not in counters:
            for c in counters.get("disks", []):
                wear = c.get("Wear")
                if isinstance(wear, (int, float)) and wear >= wear_warn_percent:
                    alerts.append({"device_id": c.get("DeviceId"), "issue": f"SSD wear at {wear}%"})
                for field in ("ReadErrorsUncorrected", "WriteErrorsUncorrected"):
                    val = c.get(field)
                    if isinstance(val, (int, float)) and val > 0:
                        alerts.append({"device_id": c.get("DeviceId"), "issue": f"{field} = {val}"})

        return {"success": True, "alerts": alerts, "count": len(alerts)}
