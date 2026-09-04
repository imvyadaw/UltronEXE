"""USB Eject Manager
====================
Lists removable/USB disks and safely ejects them - the same action as
the "Safely Remove Hardware" tray icon. Detection uses the Windows
Storage PowerShell module (Get-Disk filtered to BusType 'USB'); the
actual eject uses the classic Shell.Application COM "Eject" verb
(`Namespace(17).ParseName(drive).InvokeVerb('Eject')`), which is the
same code path Explorer itself uses for a drive's right-click >
Eject - there is no first-class PowerShell cmdlet for ejecting media,
so this is the standard, well-established way to do it from a script.

Distinct from partition_manager.py/format_manager.py (which manage a
disk's internal structure/filesystem while it's attached) - this
module is purely about the physical attach/detach lifecycle: is a
drive removable, and is it now safe to physically unplug it.

eject_drive is confirm-gated - it flushes and unmounts the volume, and
if anything on it has open handles the eject can fail or, in rare
cases with unsupported hardware, leave the volume in an inconsistent
state until replugged. Read-only listing needs no admin; eject
generally doesn't either, since it's a user-session shell action.
"""

import json
import subprocess
from typing import Dict


class UsbEjectManager:
    """List removable/USB disks and safely eject them."""

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

    def _run_json(self, script: str, timeout: float = 30.0):
        result = self._run_ps(f"{script} | ConvertTo-Json -Depth 4 -Compress", timeout)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Command failed."}
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

    def list_removable_drives(self) -> Dict:
        """List every USB-attached disk and, where mounted, its drive
        letter(s). No admin needed."""
        data = self._run_json(
            "Get-Disk | Where-Object {$_.BusType -eq 'USB'} | ForEach-Object { "
            "$disk = $_; $vols = Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue | "
            "Get-Volume -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DriveLetter; "
            "[PSCustomObject]@{ DiskNumber = $disk.Number; FriendlyName = $disk.FriendlyName; "
            "Size = $disk.Size; DriveLetters = @($vols) } }"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {"removable_drives": data, "count": len(data)}

    def get_drive_info(self, drive_letter: str) -> Dict:
        """Get details for one removable drive by its drive letter,
        including which physical disk it lives on. No admin needed."""
        letter = self._letter(drive_letter)
        data = self._run_json(
            f"$vol = Get-Volume -DriveLetter {letter}; $part = Get-Partition -DriveLetter {letter}; "
            f"$disk = Get-Disk -Number $part.DiskNumber; "
            f"[PSCustomObject]@{{ DriveLetter = '{letter}'; Label = $vol.FileSystemLabel; "
            f"Size = $vol.Size; FreeSpace = $vol.SizeRemaining; DiskNumber = $disk.Number; "
            f"BusType = $disk.BusType; FriendlyName = $disk.FriendlyName }}"
        )
        if isinstance(data, dict) and "error" in data:
            return data
        if not data:
            return {"error": f"No drive {letter}: found."}
        info = data[0]
        if info.get("BusType") != "USB":
            return {"error": f"{letter}: is not a USB-attached drive (BusType={info.get('BusType')})."}
        return info

    def eject_drive(self, drive_letter: str, confirm: bool = False) -> Dict:
        """Safely eject a removable drive by drive letter - flushes
        pending writes and detaches it, after which it's safe to
        physically unplug. Confirm-gated - fails if files on the drive
        have open handles, and rarely can leave the volume inconsistent
        on unsupported hardware if forced."""
        letter = self._letter(drive_letter)
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will safely eject {letter}: - make sure no files on it are open elsewhere first.",
            }
        result = self._run_ps(
            f"$sh = New-Object -ComObject Shell.Application; "
            f"$item = $sh.Namespace(17).ParseName('{letter}:'); "
            f"if ($item) {{ $item.InvokeVerb('Eject'); 'ok' }} else {{ 'notfound' }}"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Eject command failed."}
        if "notfound" in result["stdout"]:
            return {"error": f"Could not find drive {letter}: to eject."}
        return {"success": True, "drive_letter": letter, "ejected": True}
