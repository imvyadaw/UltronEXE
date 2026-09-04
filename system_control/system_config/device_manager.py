"""Device Manager Control
=========================
Deeper device-management control than apps/system/device_manager.py's
DeviceManagerApp (which only opens devmgmt.msc + lists devices). This
adds per-device detail, driver info, and enable/disable/rescan - all
via PowerShell's PnpDevice cmdlets, same approach DeviceManagerApp
already uses for listing.

Enable/disable a device is confirm-gated and needs admin (Enable-
PnpDevice/Disable-PnpDevice always do); errors from PowerShell are
passed through with an admin hint since there's no reliable way to
check elevation before trying.
"""

import json
import subprocess
from typing import Dict


class DeviceManagerControl:
    """List/inspect/enable/disable devices and driver info via Get/Enable/Disable-PnpDevice."""

    def _run_ps(self, cmd: str, timeout: float = 30.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
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
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_json(self, stdout: str):
        if not stdout:
            return []
        data = json.loads(stdout)
        return data if isinstance(data, list) else [data]

    def list_devices(self, only_problems: bool = False, device_class: str = "") -> Dict:
        """List devices, optionally filtered to only those with a
        non-OK status, and/or by device class (e.g. 'Net', 'USB', 'Display')."""
        filters = []
        if only_problems:
            filters.append("$_.Status -ne 'OK'")
        if device_class:
            filters.append(f"$_.Class -eq '{device_class}'")
        where = f" | Where-Object {{{' -and '.join(filters)}}}" if filters else ""
        cmd = f"Get-PnpDevice{where} | Select-Object FriendlyName,InstanceId,Status,Class | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        try:
            devices = self._parse_json(result["stdout"])
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "devices": devices, "count": len(devices)}

    def get_device_details(self, instance_id: str) -> Dict:
        """Full property set for one device (by its InstanceId, from list_devices)."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        safe_id = instance_id.replace("'", "''")
        cmd = (
            f"Get-PnpDevice -InstanceId '{safe_id}' | Get-PnpDeviceProperty "
            f"| Select-Object KeyName,Data | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Device not found: {instance_id}"}
        try:
            props = self._parse_json(result["stdout"])
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "instance_id": instance_id, "properties": props}

    def get_driver_info(self, instance_id: str) -> Dict:
        """Driver version/provider/date for one device."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        safe_id = instance_id.replace("'", "''")
        cmd = (
            f"Get-PnpDeviceProperty -InstanceId '{safe_id}' "
            f"-KeyName 'DEVPKEY_Device_DriverVersion','DEVPKEY_Device_DriverProvider','DEVPKEY_Device_DriverDate' "
            f"| Select-Object KeyName,Data | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Device not found: {instance_id}"}
        try:
            props = self._parse_json(result["stdout"])
            driver = {p.get("KeyName", ""): p.get("Data") for p in props}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "instance_id": instance_id, "driver": driver}

    def rescan_hardware(self) -> Dict:
        """Trigger a 'Scan for hardware changes' equivalent."""
        result = self._run_ps("pnputil /scan-devices")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Hardware rescan failed"}
        return {"success": True, "output": result["stdout"]}

    def enable_device(self, instance_id: str, confirm: bool = False) -> Dict:
        """Enable a disabled device. Needs admin. Confirm-gated."""
        return self._toggle_device(instance_id, enable=True, confirm=confirm)

    def disable_device(self, instance_id: str, confirm: bool = False) -> Dict:
        """Disable a device. Needs admin. Confirm-gated - disabling the
        wrong device (e.g. the keyboard/network adapter ULTRON itself
        needs) can lock out interaction, so double-check instance_id."""
        return self._toggle_device(instance_id, enable=False, confirm=confirm)

    def _toggle_device(self, instance_id: str, enable: bool, confirm: bool) -> Dict:
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enable else "disable"
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} device {instance_id} (needs admin)",
                "message": "Call again with confirm=true to apply.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enable else "Disable-PnpDevice"
        cmd = f"{verb} -InstanceId '{safe_id}' -Confirm:$false"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or f"{verb} failed"
            if "access" in err.lower() or "denied" in err.lower() or "administrat" in err.lower():
                err += " - device enable/disable needs ULTRON running as Administrator."
            return {"error": err}
        return {"success": True, "instance_id": instance_id, "action": action}
