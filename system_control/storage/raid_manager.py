"""RAID Manager (Storage Spaces)
================================
Inspects and controls Windows' built-in software-RAID equivalent,
Storage Spaces, via the Windows Storage PowerShell module (Get-
PhysicalDisk, Get-StoragePool, New-StoragePool, Get-VirtualDisk,
New-VirtualDisk, Repair-VirtualDisk, Remove-VirtualDisk, Remove-
StoragePool) - the same surface as the "Storage Spaces" Control
Panel applet. There is no hardware-RAID controller assumed; this is
purely the OS-level pooling/resiliency layer.

Distinct from partition_manager.py/format_manager.py, which operate
on a single physical disk's partitions and filesystem - a storage
pool spans multiple physical disks, and a virtual disk built on top
of a pool is itself what gets partitioned and formatted afterward.

Pooling a physical disk (create_storage_pool) claims it entirely for
Storage Spaces' use - anything on it is effectively gone from normal
Windows' view. Creating/removing virtual disks and pools is
confirm-gated and destructive for the same reason delete_partition
is in partition_manager.py. Reads need no admin; every state-changing
method needs admin.
"""

import json
import subprocess
from typing import Dict, List, Optional


class RaidManager:
    """Inspect and control Storage Spaces pools and virtual disks."""

    def _run_ps(self, script: str, timeout: float = 60.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def _run_json(self, script: str, timeout: float = 60.0):
        result = self._run_ps(f"{script} | ConvertTo-Json -Depth 4 -Compress", timeout)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Command failed.")}
        if not result["stdout"]:
            return []
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse PowerShell output."}
        return data if isinstance(data, list) else [data]

    def list_physical_disks(self) -> Dict:
        """List every physical disk visible to Storage Spaces: friendly
        name, serial, size, media type (HDD/SSD), health, and whether
        it's available to be pooled (CanPool). No admin needed."""
        data = self._run_json(
            "Get-PhysicalDisk | Select-Object FriendlyName,SerialNumber,Size,MediaType,"
            "HealthStatus,OperationalStatus,CanPool,UniqueId"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"physical_disks": data, "count": len(data)}

    def list_storage_pools(self) -> Dict:
        """List storage pools: name, size, allocated size, and health.
        Excludes the hidden 'Primordial' pool (all unpooled disks).
        No admin needed."""
        data = self._run_json(
            "Get-StoragePool | Where-Object {-not $_.IsPrimordial} | "
            "Select-Object FriendlyName,Size,AllocatedSize,HealthStatus,OperationalStatus"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"storage_pools": data, "count": len(data)}

    def get_storage_pool_info(self, name: str) -> Dict:
        """Get details for one storage pool by friendly name. No admin
        needed."""
        escaped = name.replace("'", "''")
        data = self._run_json(
            f"Get-StoragePool -FriendlyName '{escaped}' | Select-Object FriendlyName,Size,AllocatedSize,"
            f"HealthStatus,OperationalStatus,IsReadOnly"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No storage pool named {name!r} found."}
        return data[0]

    def create_storage_pool(self, name: str, physical_disk_friendly_names: List[str], confirm: bool = False) -> Dict:
        """Create a new storage pool out of one or more unpooled physical
        disks (see list_physical_disks for CanPool=True candidates).
        Confirm-gated and destructive - every disk given is claimed
        entirely for Storage Spaces and anything on it becomes
        inaccessible to normal Windows. Needs admin."""
        if not physical_disk_friendly_names:
            return {"error": "physical_disk_friendly_names must contain at least one disk."}
        disk_list = ",".join(f"'{d.replace(chr(39), chr(39)*2)}'" for d in physical_disk_friendly_names)
        escaped_name = name.replace("'", "''")
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will create storage pool {name!r} from disk(s) {', '.join(physical_disk_friendly_names)}, "
                    "claiming them entirely for Storage Spaces - anything currently on them becomes inaccessible."
                ),
            }
        script = (
            "$subsystem = Get-StorageSubSystem -FriendlyName 'Storage Spaces*'; "
            f"$disks = Get-PhysicalDisk -FriendlyName {disk_list}; "
            f"New-StoragePool -FriendlyName '{escaped_name}' -StorageSubSystemFriendlyName $subsystem.FriendlyName "
            "-PhysicalDisks $disks"
        )
        data = self._run_json(script)
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": "New-StoragePool returned no result - it may still have failed."}
        return {"success": True, "storage_pool": data[0]}

    def remove_storage_pool(self, name: str, confirm: bool = False) -> Dict:
        """Permanently delete a storage pool and every virtual disk built
        on it, along with all their data. Confirm-gated, needs admin.
        Any virtual disk on this pool must not be in use."""
        escaped = name.replace("'", "''")
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will PERMANENTLY DELETE storage pool {name!r} and all virtual disks/data on it.",
            }
        result = self._run_ps(f"Get-StoragePool -FriendlyName '{escaped}' | Remove-StoragePool -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-StoragePool failed.")}
        return {"success": True, "removed_storage_pool": name}

    def list_virtual_disks(self) -> Dict:
        """List virtual disks: name, size, resiliency type
        (Simple/Mirror/Parity), and health. No admin needed."""
        data = self._run_json(
            "Get-VirtualDisk | Select-Object FriendlyName,Size,ResiliencySettingName,"
            "HealthStatus,OperationalStatus,IsManualAttach"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"virtual_disks": data, "count": len(data)}

    def create_virtual_disk(
        self,
        pool_name: str,
        name: str,
        resiliency: str = "Mirror",
        size_bytes: Optional[int] = None,
        use_max_size: bool = False,
        confirm: bool = False,
    ) -> Dict:
        """Create a new virtual disk on an existing storage pool.
        resiliency: 'Simple' (no redundancy, like RAID 0), 'Mirror'
        (like RAID 1, needs 2+ disks in the pool), or 'Parity' (like
        RAID 5, needs 3+ disks). Once created, the virtual disk still
        needs a partition and filesystem (see partition_manager.py/
        format_manager.py) before it's usable. Confirm-gated, needs
        admin."""
        resiliency = resiliency.capitalize()
        if resiliency not in ("Simple", "Mirror", "Parity"):
            return {"error": "resiliency must be 'Simple', 'Mirror', or 'Parity'."}
        if not size_bytes and not use_max_size:
            return {"error": "Provide either size_bytes or use_max_size=True."}
        escaped_pool = pool_name.replace("'", "''")
        escaped_name = name.replace("'", "''")
        if not confirm:
            preview_size = "all remaining pool space" if use_max_size else f"{size_bytes} bytes"
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will create {resiliency} virtual disk {name!r} using {preview_size} "
                    f"on storage pool {pool_name!r}."
                ),
            }
        size_clause = "-UseMaximumSize" if use_max_size else f"-Size {size_bytes}"
        script = (
            f"New-VirtualDisk -StoragePoolFriendlyName '{escaped_pool}' -FriendlyName '{escaped_name}' "
            f"-ResiliencySettingName {resiliency} {size_clause}"
        )
        data = self._run_json(script)
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": "New-VirtualDisk returned no result - it may still have failed."}
        return {"success": True, "virtual_disk": data[0]}

    def get_virtual_disk_health(self, name: str) -> Dict:
        """Read a virtual disk's health and operational status. No admin
        needed."""
        escaped = name.replace("'", "''")
        data = self._run_json(
            f"Get-VirtualDisk -FriendlyName '{escaped}' | Select-Object FriendlyName,HealthStatus,"
            f"OperationalStatus,ResiliencySettingName"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No virtual disk named {name!r} found."}
        return data[0]

    def repair_virtual_disk(self, name: str, confirm: bool = False) -> Dict:
        """Trigger a repair of a degraded virtual disk (e.g. after
        replacing a failed drive in a Mirror/Parity pool). Confirm-gated
        - can be I/O-intensive and slow on large disks - and needs
        admin."""
        escaped = name.replace("'", "''")
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will start repairing virtual disk {name!r} - I/O-intensive and may take a long time.",
            }
        result = self._run_ps(f"Get-VirtualDisk -FriendlyName '{escaped}' | Repair-VirtualDisk")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Repair-VirtualDisk failed.")}
        return {"success": True, "repairing": name}

    def remove_virtual_disk(self, name: str, confirm: bool = False) -> Dict:
        """Permanently delete a virtual disk and all its data. Confirm-
        gated, destructive, needs admin. The underlying storage pool
        survives and can host new virtual disks afterward."""
        escaped = name.replace("'", "''")
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will PERMANENTLY DELETE virtual disk {name!r} and all data on it.",
            }
        result = self._run_ps(f"Get-VirtualDisk -FriendlyName '{escaped}' | Remove-VirtualDisk -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-VirtualDisk failed.")}
        return {"success": True, "removed_virtual_disk": name}
