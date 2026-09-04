"""USB Control
=============
USB-specific power management and mass-storage policy - distinct from
system_control/system_config/device_manager.py (generic PnP enable/
disable for *any* device class, which this module calls into for USB
devices rather than re-implementing) and from system_control/storage/
usb_eject.py (physical attach/detach lifecycle of removable *disks*
specifically, via the Shell "Eject" verb - this module never touches
that path). What's left, and what this module actually owns:
enumerating USB controllers/hubs/devices as a category, per-device
"allow the computer to turn this device off to save power" (USB
selective suspend), and the system-wide policy for whether USB mass-
storage devices are allowed to mount at all.

Selective-suspend reads/writes go through the device's power-
management CIM class (`MSPower_DeviceEnable`) keyed to the same
InstanceId `Get-PnpDevice` uses. Mass-storage policy is the well-known
enterprise/parental-control registry lever (`HKLM\\SYSTEM\\
CurrentControlSet\\Services\\USBSTOR` Start value: 3 = allowed on next
plug-in, 4 = disabled) - this changes whether new USB storage devices
are allowed to mount, not whether the USB *ports* themselves work.

Every state-changing method here is confirm-gated. Disabling USB
mass storage system-wide is broad (affects every future USB drive,
not just one) and disabling selective suspend on a device already
in use can briefly interrupt it.
"""

import subprocess
import winreg
from typing import Dict

_USBSTOR_PATH = r"SYSTEM\CurrentControlSet\Services\USBSTOR"


class USBControl:
    """USB device enumeration, per-device selective-suspend power
    management, and system-wide USB mass-storage mount policy."""

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

    def list_usb_devices(self) -> Dict:
        """All currently-known USB devices (controllers, hubs, and
        attached peripherals): friendly name, InstanceId, and status.
        Use the returned InstanceId with the device_manager.py's
        enable/disable, or with this module's selective-suspend
        methods below. No admin needed."""
        result = self._run_ps(
            "Get-PnpDevice -Class USB, USBDevice -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        if not result["stdout"]:
            return {"success": True, "devices": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse device list"}
        devices = data if isinstance(data, list) else [data]
        return {"success": True, "devices": devices, "count": len(devices)}

    def get_selective_suspend(self, instance_id: str) -> Dict:
        """Whether 'Allow the computer to turn off this device to save
        power' is on for a given device (by InstanceId, from
        list_usb_devices). No admin needed."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        safe_id = instance_id.replace("'", "''")
        result = self._run_ps(
            f"Get-CimInstance MSPower_DeviceEnable -Namespace root/wmi | "
            f"Where-Object {{ $_.InstanceName -like '*{safe_id}*' }} | "
            f"Select-Object InstanceName, Enable | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not query power management state"}
        if not result["stdout"]:
            return {
                "error": f"No power-management entry found for '{instance_id}' - this device may not support selective suspend."
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse power management state"}
        entry = data[0] if isinstance(data, list) else data
        return {"success": True, "instance_id": instance_id, "selective_suspend_enabled": bool(entry.get("Enable"))}

    def set_selective_suspend(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Turn 'Allow the computer to turn off this device to save
        power' on/off for a device (by InstanceId). Confirm-gated -
        can briefly interrupt the device if it's actively in use when
        toggled. Needs admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} USB selective suspend (power-saving) for device {instance_id}.",
            }
        safe_id = instance_id.replace("'", "''")
        script = (
            f"$dev = Get-CimInstance MSPower_DeviceEnable -Namespace root/wmi | "
            f"Where-Object {{ $_.InstanceName -like '*{safe_id}*' }}; "
            f"if (-not $dev) {{ throw 'not found' }}; "
            f"Set-CimInstance -InputObject $dev -Property @{{Enable=${'true' if enabled else 'false'}}}"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or f"Could not {action} selective suspend"
            if "not found" in err.lower():
                err = f"No power-management entry found for '{instance_id}' - this device may not support selective suspend."
            elif "access" in err.lower() or "denied" in err.lower():
                err += " - run ULTRON as Administrator."
            return {"error": err}
        return {"success": True, "instance_id": instance_id, "selective_suspend_enabled": enabled}

    def get_mass_storage_policy(self) -> Dict:
        """Whether new USB mass-storage (flash drives, external HDDs)
        devices are currently allowed to mount system-wide. No admin
        needed to read."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _USBSTOR_PATH) as key:
                start, _ = winreg.QueryValueEx(key, "Start")
                return {"success": True, "mass_storage_allowed": start == 3, "raw_start_value": start}
        except FileNotFoundError:
            return {"error": "USBSTOR service key not found - unexpected on a standard Windows install."}
        except OSError as e:
            return {"error": str(e)}

    def set_mass_storage_policy(self, allowed: bool, confirm: bool = False) -> Dict:
        """Allow or block new USB mass-storage devices from mounting,
        system-wide (Start=3 allowed, Start=4 disabled). This is
        broad - it affects every USB drive plugged in from now on
        (already-mounted drives are unaffected until unplugged/
        replugged), which is exactly the lever IT/parental-control
        tools use for this. Confirm-gated, needs admin."""
        if not confirm:
            action = "allow" if allowed else "block"
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} USB mass-storage devices (flash drives, external HDDs) from mounting, "
                f"system-wide, from now on. Needs Administrator.",
            }
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _USBSTOR_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Start", 0, winreg.REG_DWORD, 3 if allowed else 4)
            return {"success": True, "mass_storage_allowed": allowed}
        except PermissionError:
            return {"error": "Access denied - run ULTRON as Administrator to change USB mass-storage policy."}
        except OSError as e:
            return {"error": str(e)}
