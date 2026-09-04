"""Partition Manager
====================
Inspects and controls disks and partitions via the Windows Storage
PowerShell module (Get-Disk, Get-Partition, Get-Volume, Resize-
Partition, New-Partition, Remove-Partition, Set-Partition,
Initialize-Disk) - the same surface as Disk Management
(diskmgmt.msc). Needs admin for every state-changing method; reads
(list_disks, list_partitions, list_volumes, get_resize_limits) do not.

Distinct from format_manager.py (what filesystem lives ON a partition,
and erasing its content) - this module is the partition TABLE: which
partitions exist, their size/boundaries, and drive-letter assignment.
Distinct from system_control/files/ (operations on files once a
filesystem is already mounted, not the partition itself).

Every method that changes the partition table is DESTRUCTIVE or
disruptive in a way that's hard or impossible to undo without a backup
- delete_partition and initialize_disk erase data outright, create_
partition and resize_partition rewrite the partition table, and
assign/remove_drive_letter can break shortcuts, mapped paths, and
running programs that reference the old letter. All of them are
confirm-gated with a preview describing exactly what will happen.
"""

import json
import subprocess
from typing import Dict, Optional


class PartitionManager:
    """Inspect and control disks and partitions via the Storage PowerShell module."""

    def _run_ps(self, script: str, timeout: float = 30.0) -> Dict:
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

    def _run_json(self, script: str, timeout: float = 30.0):
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

    def list_disks(self) -> Dict:
        """List every physical disk: number, friendly name, size, partition
        style (MBR/GPT), and health/operational status. No admin needed."""
        data = self._run_json(
            "Get-Disk | Select-Object Number,FriendlyName,Size,PartitionStyle,OperationalStatus,HealthStatus,IsBoot,IsSystem"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"disks": data, "count": len(data)}

    def get_disk_info(self, disk_number: int) -> Dict:
        """Get details for one disk by its Get-Disk number. No admin needed."""
        data = self._run_json(
            f"Get-Disk -Number {disk_number} | Select-Object Number,FriendlyName,Size,AllocatedSize,"
            f"PartitionStyle,OperationalStatus,HealthStatus,IsBoot,IsSystem,BusType"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No disk numbered {disk_number} found."}
        return data[0]

    def list_partitions(self, disk_number: Optional[int] = None) -> Dict:
        """List partitions, optionally filtered to one disk. No admin needed."""
        filt = f"-DiskNumber {disk_number}" if disk_number is not None else ""
        data = self._run_json(
            f"Get-Partition {filt} | Select-Object DiskNumber,PartitionNumber,DriveLetter,Size,Type,IsBoot,IsSystem,IsActive,Offset"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"partitions": data, "count": len(data)}

    def get_partition_info(self, disk_number: int, partition_number: int) -> Dict:
        """Get details for one partition. No admin needed."""
        data = self._run_json(
            f"Get-Partition -DiskNumber {disk_number} -PartitionNumber {partition_number} | "
            f"Select-Object DiskNumber,PartitionNumber,DriveLetter,Size,Type,IsBoot,IsSystem,IsActive,Offset,GptType,MbrType"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No partition {partition_number} found on disk {disk_number}."}
        return data[0]

    def list_volumes(self) -> Dict:
        """List volumes: drive letter, label, filesystem, size, and free
        space. No admin needed."""
        data = self._run_json(
            "Get-Volume | Select-Object DriveLetter,FileSystemLabel,FileSystem,Size,SizeRemaining,HealthStatus"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"volumes": data, "count": len(data)}

    def get_free_space(self, drive_letter: str) -> Dict:
        """Read total size and remaining free space for a drive letter,
        e.g. 'C'. No admin needed."""
        letter = drive_letter.strip().rstrip(":")
        data = self._run_json(f"Get-Volume -DriveLetter {letter} | Select-Object Size,SizeRemaining")
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No volume {letter}: found."}
        return {"drive_letter": letter, "size_bytes": data[0].get("Size"), "free_bytes": data[0].get("SizeRemaining")}

    def get_resize_limits(self, disk_number: int, partition_number: int) -> Dict:
        """Read the minimum and maximum size a partition can be resized
        to right now, given surrounding free space and its data usage.
        No admin needed."""
        data = self._run_json(
            f"Get-PartitionSupportedSize -DiskNumber {disk_number} -PartitionNumber {partition_number}"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"Could not compute resize limits for partition {partition_number} on disk {disk_number}."}
        return {
            "disk_number": disk_number,
            "partition_number": partition_number,
            "min_size_bytes": data[0].get("SizeMin"),
            "max_size_bytes": data[0].get("SizeMax"),
        }

    def resize_partition(
        self, disk_number: int, partition_number: int, new_size_bytes: int, confirm: bool = False
    ) -> Dict:
        """Resize (shrink or extend) a partition to an exact byte size.
        Call get_resize_limits first to stay within what's actually
        possible. Confirm-gated - rewrites the partition table and needs
        admin; shrinking below used space can fail or truncate data."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will resize partition {partition_number} on disk {disk_number} to {new_size_bytes} bytes.",
            }
        result = self._run_ps(
            f"Resize-Partition -DiskNumber {disk_number} -PartitionNumber {partition_number} -Size {new_size_bytes}"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Resize-Partition failed.")}
        return {
            "success": True,
            "disk_number": disk_number,
            "partition_number": partition_number,
            "new_size_bytes": new_size_bytes,
        }

    def assign_drive_letter(self, disk_number: int, partition_number: int, letter: str, confirm: bool = False) -> Dict:
        """Assign a drive letter to a partition. Confirm-gated - needs
        admin, and can break shortcuts/mapped paths that reference
        whatever letter (or lack of one) the partition had before."""
        letter = letter.strip().rstrip(":").upper()
        if len(letter) != 1 or not letter.isalpha():
            return {"error": "letter must be a single drive letter, e.g. 'E'."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will assign drive letter {letter}: to partition {partition_number} on disk {disk_number}.",
            }
        result = self._run_ps(
            f"Set-Partition -DiskNumber {disk_number} -PartitionNumber {partition_number} -NewDriveLetter {letter}"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Set-Partition failed.")}
        return {
            "success": True,
            "disk_number": disk_number,
            "partition_number": partition_number,
            "drive_letter": letter,
        }

    def remove_drive_letter(self, disk_number: int, partition_number: int, confirm: bool = False) -> Dict:
        """Remove a partition's drive letter (it stays mounted internally,
        just becomes inaccessible by letter). Confirm-gated - needs admin
        and can break shortcuts/mapped paths pointing at that letter."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will remove the drive letter from partition {partition_number} on disk {disk_number}.",
            }
        info = self.get_partition_info(disk_number, partition_number)
        if "error" in info:
            return info
        letter = info.get("DriveLetter")
        if not letter:
            return {"error": "This partition has no drive letter assigned."}
        result = self._run_ps(
            f'Remove-PartitionAccessPath -DiskNumber {disk_number} -PartitionNumber {partition_number} -AccessPath "{letter}:\\"'
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-PartitionAccessPath failed.")}
        return {
            "success": True,
            "disk_number": disk_number,
            "partition_number": partition_number,
            "removed_letter": letter,
        }

    def create_partition(
        self,
        disk_number: int,
        size_bytes: Optional[int] = None,
        use_max_size: bool = False,
        drive_letter: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict:
        """Create a new partition in a disk's unallocated space, either
        an exact size_bytes or use_max_size=True to take all remaining
        free space. Confirm-gated - rewrites the partition table and
        needs admin."""
        if not size_bytes and not use_max_size:
            return {"error": "Provide either size_bytes or use_max_size=True."}
        size_clause = "-UseMaximumSize" if use_max_size else f"-Size {size_bytes}"
        letter_clause = (
            f"-DriveLetter {drive_letter.strip().rstrip(':').upper()}" if drive_letter else "-AssignDriveLetter"
        )
        if not confirm:
            preview_size = "all remaining free space" if use_max_size else f"{size_bytes} bytes"
            return {
                "requires_confirmation": True,
                "preview": f"This will create a new partition on disk {disk_number} using {preview_size}.",
            }
        data = self._run_json(f"New-Partition -DiskNumber {disk_number} {size_clause} {letter_clause}")
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": "New-Partition returned no result - it may still have failed."}
        return {"success": True, "disk_number": disk_number, "partition": data[0]}

    def delete_partition(self, disk_number: int, partition_number: int, confirm: bool = False) -> Dict:
        """Permanently delete a partition and ALL its data. Confirm-gated
        - this is destructive and needs admin. There is no undo short of
        a prior backup or data-recovery software."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will PERMANENTLY DELETE partition {partition_number} on disk {disk_number} and everything on it.",
            }
        result = self._run_ps(
            f"Remove-Partition -DiskNumber {disk_number} -PartitionNumber {partition_number} -Confirm:$false"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-Partition failed.")}
        return {"success": True, "deleted_disk_number": disk_number, "deleted_partition_number": partition_number}

    def initialize_disk(self, disk_number: int, style: str = "GPT", confirm: bool = False) -> Dict:
        """Initialize a raw/uninitialized disk with a new partition table
        (GPT or MBR), WIPING any existing partition table. Confirm-gated
        - destructive and needs admin; only run this on a disk you've
        confirmed via list_disks is actually raw/empty."""
        style = style.upper()
        if style not in ("GPT", "MBR"):
            return {"error": "style must be 'GPT' or 'MBR'."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will initialize disk {disk_number} as {style}, WIPING its existing partition table if any.",
            }
        result = self._run_ps(f"Initialize-Disk -Number {disk_number} -PartitionStyle {style} -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Initialize-Disk failed.")}
        return {"success": True, "disk_number": disk_number, "partition_style": style}

    def set_partition_active(
        self, disk_number: int, partition_number: int, active: bool = True, confirm: bool = False
    ) -> Dict:
        """Mark an MBR partition active/inactive (the BIOS-boot flag - has
        no effect on GPT disks, which use the EFI System Partition
        instead). Confirm-gated - changing the active partition on the
        boot disk can make the system unbootable."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will mark partition {partition_number} on disk {disk_number} as "
                    f"{'active' if active else 'inactive'} - if this is the boot disk, get this wrong and the "
                    "machine may not boot."
                ),
            }
        result = self._run_ps(
            f"Set-Partition -DiskNumber {disk_number} -PartitionNumber {partition_number} -IsActive ${'true' if active else 'false'}"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Set-Partition -IsActive failed.")}
        return {"success": True, "disk_number": disk_number, "partition_number": partition_number, "is_active": active}
