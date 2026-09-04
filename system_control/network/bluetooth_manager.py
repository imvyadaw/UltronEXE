"""Bluetooth Manager
=====================
Windows Bluetooth radio and paired-device control via PowerShell
(Windows.Devices.* WinRT projection + PnP device cmdlets). Distinct
from the top-level networking/ package (protocol clients) and from
system_control/network's Wi-Fi/Ethernet/VPN managers - this one talks
to the Bluetooth radio and its paired-device list, not IP networking.

Listing paired devices and radio state are plain reads. Enabling/
disabling the radio and removing a paired device are confirm-gated -
same pattern as every other state-changing tool in this codebase.
Pairing a *new* device from scratch needs the Windows "Add a device"
UI/consent flow (no supported headless CLI path), so pair_new_device()
opens that settings page rather than silently completing a pairing.
"""

import subprocess
import re
from typing import Dict

_PS_LIST_DEVICES = (
    "Get-PnpDevice -Class Bluetooth | "
    "Select-Object FriendlyName, InstanceId, Status | "
    "ConvertTo-Csv -NoTypeInformation"
)

_PS_LIST_RADIO = (
    "Get-PnpDevice -Class Bluetooth -Status OK | "
    "Where-Object { $_.FriendlyName -match 'Radio|Adapter' } | "
    "Select-Object FriendlyName, InstanceId, Status | "
    "ConvertTo-Csv -NoTypeInformation"
)


class BluetoothManager:
    """Inspect and control the Bluetooth radio and paired devices via PowerShell/PnP."""

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
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

    def _parse_csv(self, csv_text: str) -> list:
        lines = [l for l in csv_text.splitlines() if l.strip()]
        if len(lines) < 2:
            return []
        import csv as _csv
        import io

        reader = _csv.DictReader(io.StringIO("\n".join(lines)))
        return [dict(row) for row in reader]

    def get_radio_status(self) -> Dict:
        """Check whether a Bluetooth radio is present and enabled."""
        result = self._run_ps(_PS_LIST_RADIO)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "PowerShell query failed")}
        rows = self._parse_csv(result["stdout"])
        if not rows:
            return {"present": False, "message": "No Bluetooth radio found on this machine."}
        radio = rows[0]
        return {
            "present": True,
            "name": radio.get("FriendlyName"),
            "enabled": radio.get("Status", "").strip('"') == "OK",
            "status": radio.get("Status"),
        }

    def set_radio_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable the Bluetooth radio. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'enable' if enabled else 'disable'} the Bluetooth radio, "
                f"{'restoring' if enabled else 'dropping'} all Bluetooth connections.",
            }
        radio = self.get_radio_status()
        if "error" in radio:
            return radio
        if not radio.get("present"):
            return {"error": "No Bluetooth radio found on this machine."}
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        script = (
            f"Get-PnpDevice -Class Bluetooth | Where-Object "
            f"{{ $_.FriendlyName -match 'Radio|Adapter' }} | "
            f"{verb} -Confirm:$false"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"{verb} failed")}
        return {"success": True, "enabled": enabled}

    def list_paired_devices(self) -> Dict:
        """List Bluetooth devices currently paired with this machine."""
        result = self._run_ps(_PS_LIST_DEVICES)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "PowerShell query failed")}
        rows = self._parse_csv(result["stdout"])
        devices = [
            {
                "name": r.get("FriendlyName"),
                "instance_id": r.get("InstanceId"),
                "connected": r.get("Status", "").strip('"') == "OK",
            }
            for r in rows
            if not re.search(r"Radio|Adapter|Enumerator", r.get("FriendlyName", ""), re.I)
        ]
        return {"devices": devices, "count": len(devices)}

    def get_device_status(self, name: str) -> Dict:
        """Get connection status for a specific paired device by (partial) name."""
        listed = self.list_paired_devices()
        if "error" in listed:
            return listed
        for d in listed["devices"]:
            if d["name"] and name.lower() in d["name"].lower():
                return d
        return {"error": f"No paired device matching '{name}' found."}

    def connect_device(self, name: str, confirm: bool = False) -> Dict:
        """Reconnect a previously paired Bluetooth device by name. Confirm-gated."""
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will attempt to reconnect '{name}'."}
        device = self.get_device_status(name)
        if "error" in device:
            return device
        script = f"Enable-PnpDevice -InstanceId '{device['instance_id']}' -Confirm:$false"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Connect failed")}
        return {"success": True, "device": device["name"]}

    def disconnect_device(self, name: str, confirm: bool = False) -> Dict:
        """Disconnect (without unpairing) a Bluetooth device by name. Confirm-gated."""
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will disconnect '{name}' (stays paired)."}
        device = self.get_device_status(name)
        if "error" in device:
            return device
        script = f"Disable-PnpDevice -InstanceId '{device['instance_id']}' -Confirm:$false"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Disconnect failed")}
        return {"success": True, "device": device["name"]}

    def remove_paired_device(self, name: str, confirm: bool = False) -> Dict:
        """Forget/unpair a Bluetooth device entirely. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will unpair '{name}' - you'll need to pair it again from scratch to reuse it.",
            }
        device = self.get_device_status(name)
        if "error" in device:
            return device
        script = f"Get-PnpDevice -InstanceId '{device['instance_id']}' | Remove-PnpDevice -Confirm:$false"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": self._admin_hint(result["stderr"] or "Unpair failed - Remove-PnpDevice needs Windows 10 21H1+")
            }
        return {"success": True, "removed": device["name"]}

    def pair_new_device(self) -> Dict:
        """Open Windows' 'Add a device' Bluetooth settings page for a new pairing.
        No supported headless CLI exists for first-time pairing/consent, so this
        opens the UI flow instead of silently completing it."""
        try:
            subprocess.Popen(["start", "ms-settings:bluetooth"], shell=True)
            return {"success": True, "message": "Opened Bluetooth settings - select the new device there to pair."}
        except Exception as e:
            return {"error": str(e)}
