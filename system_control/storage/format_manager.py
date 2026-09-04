"""Format Manager
=================
Inspects and controls what's ON a partition once it exists: formatting
a volume, its filesystem type, label, allocation unit size, one-way
FAT32->NTFS conversion, and running chkdsk. Uses the Windows Storage
PowerShell module (Get-Volume, Format-Volume, Set-Volume) plus the
classic `convert.exe` and `chkdsk.exe` CLIs - the same surface as
right-clicking a drive in File Explorer and choosing Format/Properties.

Distinct from partition_manager.py (the partition TABLE - which
partitions exist and their size/boundaries) - this module is what
filesystem lives on top of a partition and that filesystem's content
and health, not the partition itself.

get_volume_info and get_filesystem_type need no admin. format_volume
is confirm-gated with a loud preview - it ERASES ALL DATA on the
volume and needs admin. convert_filesystem is confirm-gated - the
FAT32->NTFS conversion is one-way and needs admin. check_disk with
fix_errors=True is confirm-gated - fixing errors on a volume in use
requires an exclusive lock and may schedule a restart; a plain
read-only scan (fix_errors=False) is not confirm-gated. set_volume_
label is a low-risk, reversible cosmetic change and is not confirm-
gated.
"""

import json
import subprocess
from typing import Dict, Optional


class FormatManager:
    """Inspect and control volume formatting, filesystem type, and disk checks."""

    def _run(self, cmd, timeout: float = 30.0, shell: bool = False) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=shell)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "Command not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_ps(self, script: str, timeout: float = 60.0) -> Dict:
        return self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout)

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

    @staticmethod
    def _letter(drive_letter: str) -> str:
        return drive_letter.strip().rstrip(":").upper()

    def get_volume_info(self, drive_letter: str) -> Dict:
        """Read a volume's filesystem, label, size, free space, and
        health status. No admin needed."""
        letter = self._letter(drive_letter)
        data = self._run_json(
            f"Get-Volume -DriveLetter {letter} | Select-Object DriveLetter,FileSystemLabel,FileSystem,"
            f"FileSystemType,Size,SizeRemaining,HealthStatus,AllocationUnitSize"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No volume {letter}: found."}
        return data[0]

    def get_filesystem_type(self, drive_letter: str) -> Dict:
        """Read just a volume's filesystem type (e.g. 'NTFS', 'FAT32',
        'exFAT', 'ReFS'). No admin needed."""
        info = self.get_volume_info(drive_letter)
        if "error" in info:
            return info
        return {"drive_letter": self._letter(drive_letter), "file_system": info.get("FileSystem")}

    def get_allocation_unit_size(self, drive_letter: str) -> Dict:
        """Read a volume's allocation unit (cluster) size in bytes. No
        admin needed."""
        info = self.get_volume_info(drive_letter)
        if "error" in info:
            return info
        return {
            "drive_letter": self._letter(drive_letter),
            "allocation_unit_size_bytes": info.get("AllocationUnitSize"),
        }

    def set_volume_label(self, drive_letter: str, label: str) -> Dict:
        """Rename a volume's label. Not confirm-gated - cosmetic and
        instantly reversible."""
        letter = self._letter(drive_letter)
        escaped = label.replace("'", "''")
        result = self._run_ps(f"Set-Volume -DriveLetter {letter} -NewFileSystemLabel '{escaped}'")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Set-Volume failed.")}
        return {"success": True, "drive_letter": letter, "label": label}

    def format_volume(
        self,
        drive_letter: str,
        file_system: str = "NTFS",
        label: Optional[str] = None,
        quick: bool = True,
        allocation_unit_size_bytes: Optional[int] = None,
        confirm: bool = False,
    ) -> Dict:
        """Format a volume, ERASING ALL ITS DATA, and give it a new
        filesystem/label. quick=True does a quick format (default,
        fast, doesn't scan for bad sectors); quick=False does a full
        format (slow, scans the whole volume). Confirm-gated - this is
        one of the most destructive operations in this codebase and
        needs admin."""
        letter = self._letter(drive_letter)
        fs = file_system.upper()
        if fs not in ("NTFS", "FAT32", "EXFAT", "REFS"):
            return {"error": "file_system must be one of NTFS, FAT32, exFAT, ReFS."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will FORMAT {letter}: as {fs} ({'quick' if quick else 'full'} format), "
                    f"ERASING ALL DATA currently on it{f' and labeling it {label!r}' if label else ''}."
                ),
            }
        parts = [f"Format-Volume -DriveLetter {letter} -FileSystem {fs} -Confirm:$false"]
        parts.append("-Full" if not quick else "-ShortFileNameSupport:$false")
        if label:
            escaped = label.replace("'", "''")
            parts.append(f"-NewFileSystemLabel '{escaped}'")
        if allocation_unit_size_bytes:
            parts.append(f"-AllocationUnitSize {allocation_unit_size_bytes}")
        result = self._run_ps(" ".join(parts), timeout=1800.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Format-Volume failed.")}
        return {"success": True, "drive_letter": letter, "file_system": fs, "label": label, "quick": quick}

    def convert_filesystem(self, drive_letter: str, target_file_system: str = "NTFS", confirm: bool = False) -> Dict:
        """Convert a FAT32/exFAT volume to NTFS in place, preserving
        files (via convert.exe). One-way - there's no built-in tool to
        convert back without reformatting. Confirm-gated and needs
        admin."""
        letter = self._letter(drive_letter)
        target = target_file_system.upper()
        if target != "NTFS":
            return {"error": "convert.exe only supports converting TO NTFS."}
        current = self.get_filesystem_type(drive_letter)
        if "error" in current:
            return current
        if current.get("file_system", "").upper() == "NTFS":
            return {"error": f"{letter}: is already NTFS."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will convert {letter}: from {current.get('file_system')} to NTFS - this is one-way and cannot be undone without reformatting.",
            }
        result = self._run(["convert", f"{letter}:", "/FS:NTFS"], timeout=1800.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or result["stdout"] or "convert.exe failed.")}
        return {"success": True, "drive_letter": letter, "converted_to": "NTFS"}

    def check_disk(self, drive_letter: str, fix_errors: bool = False, confirm: bool = False) -> Dict:
        """Run chkdsk on a volume. fix_errors=False (default) does a
        read-only scan and is NOT confirm-gated. fix_errors=True is
        confirm-gated - it needs an exclusive lock on the volume (which
        for the system drive means scheduling the check for next
        restart) and needs admin."""
        letter = self._letter(drive_letter)
        if not fix_errors:
            result = self._run(["chkdsk", f"{letter}:"], timeout=600.0)
            if "error" in result:
                return result
            return {
                "success": True,
                "drive_letter": letter,
                "mode": "scan_only",
                "output": result["stdout"] or result["stderr"],
            }
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will run chkdsk /f on {letter}: to fix errors - needs exclusive access, and if this is "
                    "the system drive it will schedule the check for the next restart instead of running now."
                ),
            }
        result = self._run(["chkdsk", f"{letter}:", "/f"], timeout=1800.0)
        if "error" in result:
            return result
        return {
            "success": True,
            "drive_letter": letter,
            "mode": "fix_errors",
            "output": result["stdout"] or result["stderr"],
        }
