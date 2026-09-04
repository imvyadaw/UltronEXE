"""ISO / VHD Mount Manager
==========================
Mounts and dismounts disk image files - ISO, VHD, and VHDX - via the
Windows Storage PowerShell module (Mount-DiskImage, Dismount-
DiskImage, Get-DiskImage), the same mechanism as double-clicking an
.iso in File Explorer or "Mount" in its right-click menu. VHD/VHDX
*creation* and *resizing* (New-VHD, Resize-VHD) additionally need the
Hyper-V PowerShell module, which isn't present on every Windows
edition (e.g. Home) - those methods return a clear error if it's
missing rather than failing obscurely.

Distinct from partition_manager.py/format_manager.py, which operate
on disks/partitions that are already attached to the system - a
mounted image *becomes* a new disk that those modules can then act
on. Distinct from raid_manager.py (Storage Spaces pools/virtual
disks) - a VHD here is a standalone image file, not a pooled virtual
disk, though a VHD can itself be built on top of a virtual disk's
volume.

Mounting/dismounting/inspecting an image is non-destructive and
reversible (equivalent to inserting/ejecting a disc) and is not
confirm-gated. Creating a new VHD file is also not confirm-gated,
since it only fails if the target path already exists. Resizing an
existing VHD IS confirm-gated, since shrinking can fail or truncate
data. No method needs admin for ISOs; VHD/VHDX operations may need
admin depending on the target path.
"""

import json
import os
import subprocess
from typing import Dict


class IsoVhdMount:
    """Mount, dismount, and manage ISO/VHD/VHDX disk image files."""

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
        if err and "hyper-v" in err.lower():
            return (
                err
                + " - the Hyper-V PowerShell module is required for VHD creation/resizing and isn't available on this Windows edition."
            )
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

    @staticmethod
    def _esc(path: str) -> str:
        return path.replace("'", "''")

    def mount_image(self, path: str, read_only: bool = True) -> Dict:
        """Mount an ISO or VHD/VHDX, attaching it as a new disk with its
        own drive letter. Returns the assigned drive letter where
        possible. Not confirm-gated - fully reversible via
        dismount_image()."""
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        ro_clause = "-Access ReadOnly" if read_only else ""
        script = f"Mount-DiskImage -ImagePath '{self._esc(path)}' {ro_clause} -PassThru | Get-Volume"
        data = self._run_json(script)
        if isinstance(data, dict) and "error" in data:
            return data
        drive_letter = data[0].get("DriveLetter") if data else None
        return {"success": True, "path": path, "drive_letter": drive_letter}

    def dismount_image(self, path: str) -> Dict:
        """Dismount a previously mounted ISO or VHD/VHDX by its file
        path."""
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        result = self._run_ps(f"Dismount-DiskImage -ImagePath '{self._esc(path)}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Dismount-DiskImage failed.")}
        return {"success": True, "path": path, "dismounted": True}

    def get_image_info(self, path: str) -> Dict:
        """Read an image's attach state, type (ISO/VHD/VHDX), and size."""
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        data = self._run_json(
            f"Get-DiskImage -ImagePath '{self._esc(path)}' | Select-Object ImagePath,Attached,StorageType,Size"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"Could not read image info for {path}."}
        return data[0]

    def list_mounted_images(self) -> Dict:
        """List every currently mounted (attached) disk image."""
        data = self._run_json("Get-DiskImage | Where-Object {$_.Attached} | Select-Object ImagePath,StorageType,Size")
        if isinstance(data, dict) and "error" in data:
            return data
        return {"mounted_images": data, "count": len(data)}

    def create_vhd(self, path: str, size_bytes: int, dynamic: bool = True) -> Dict:
        """Create a new blank VHD or VHDX file (determined by the file
        extension in path). Requires the Hyper-V PowerShell module.
        Not confirm-gated - fails cleanly if the file already exists
        rather than overwriting it."""
        if os.path.exists(path):
            return {"error": f"{path} already exists - choose a new path or delete it first."}
        type_clause = "-Dynamic" if dynamic else "-Fixed"
        script = f"New-VHD -Path '{self._esc(path)}' -SizeBytes {size_bytes} {type_clause}"
        data = self._run_json(script)
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": "New-VHD returned no result - it may still have failed."}
        return {"success": True, "path": path, "size_bytes": size_bytes, "dynamic": dynamic}

    def get_vhd_info(self, path: str) -> Dict:
        """Read a VHD/VHDX's size, attach state, and parent (for
        differencing disks). Requires the Hyper-V PowerShell module."""
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        data = self._run_json(
            f"Get-VHD -Path '{self._esc(path)}' | Select-Object Path,Size,FileSize,VhdType,Attached,ParentPath"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"Could not read VHD info for {path}."}
        return data[0]

    def resize_vhd(self, path: str, new_size_bytes: int, confirm: bool = False) -> Dict:
        """Resize an existing VHD/VHDX. Requires the Hyper-V PowerShell
        module. Confirm-gated - shrinking below the disk's used space
        can fail or truncate data; the VHD should be dismounted first."""
        if not os.path.exists(path):
            return {"error": f"File not found: {path}"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will resize {path} to {new_size_bytes} bytes - shrinking below used space can fail "
                    "or truncate data. Make sure it's dismounted first."
                ),
            }
        result = self._run_ps(f"Resize-VHD -Path '{self._esc(path)}' -SizeBytes {new_size_bytes}")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Resize-VHD failed.")}
        return {"success": True, "path": path, "new_size_bytes": new_size_bytes}
