"""BIOS / UEFI
==============
Read-heavy wrapper around firmware info (BIOS manufacturer/version/
serial, BIOS vs UEFI firmware type, Secure Boot state, TPM presence)
plus the one action that touches firmware: rebooting straight into the
firmware setup screen (the same thing Settings > Recovery > Advanced
startup > Restart now > Troubleshoot > UEFI Firmware Settings does).

There is no programmatic way to change individual BIOS/UEFI settings
from Windows (those live outside the OS, on the firmware's own menu) -
ULTRON can only report on them and hand the user off to that menu,
same boundary windows/system_info/diagnostics.py already draws for
other low-level hardware info.

All info methods shell out to PowerShell/WMI, same approach as
system_properties.py and device_manager.py. restart_to_firmware_settings
is confirm-gated like every other reboot-triggering tool in this
codebase (mirrors restart_pc elsewhere) since it interrupts whatever
the user is doing immediately.
"""

import json
import subprocess
from typing import Dict


class BiosUefi:
    """BIOS/UEFI/Secure-Boot/TPM info, plus reboot-to-firmware-settings."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
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

    def get_bios_info(self) -> Dict:
        """BIOS manufacturer, version, serial number, release date, SMBIOS version."""
        cmd = (
            "Get-CimInstance Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion,"
            "SerialNumber,ReleaseDate,Version | ConvertTo-Json"
        )
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-CimInstance Win32_BIOS failed"}
        try:
            info = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "bios_info": info}

    def get_firmware_type(self) -> Dict:
        """Whether the machine boots via legacy BIOS or UEFI firmware."""
        cmd = "$env:firmware_type"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        raw = (result.get("stdout") or "").strip().upper()
        if not raw:
            # Fallback for shells where the env var isn't exposed.
            cmd2 = (
                "(Get-CimInstance -ClassName Win32_ComputerSystem).BootupState; "
                "[Environment]::GetEnvironmentVariable('firmware_type')"
            )
            result2 = self._run_ps(cmd2)
            raw = (result2.get("stdout") or "").strip().upper()
        is_uefi = "UEFI" in raw
        return {
            "success": True,
            "firmware_type": "UEFI" if is_uefi else ("Legacy BIOS" if raw else "Unknown"),
            "raw": raw,
        }

    def get_secure_boot_status(self) -> Dict:
        """Secure Boot on/off. Only meaningful on UEFI firmware - returns a
        clear message (not an error) on legacy BIOS machines, since
        Confirm-SecureBootUEFI itself throws there."""
        cmd = "try { Confirm-SecureBootUEFI } catch { 'NOT_UEFI' }"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        raw = (result.get("stdout") or "").strip()
        if raw == "NOT_UEFI" or not raw:
            return {
                "success": True,
                "secure_boot_supported": False,
                "message": "Secure Boot is only available on UEFI firmware - this machine "
                "is either legacy BIOS or Secure Boot state could not be read.",
            }
        return {"success": True, "secure_boot_supported": True, "secure_boot_enabled": raw.lower() == "true"}

    def get_tpm_status(self) -> Dict:
        """TPM presence/version/enabled state, if any."""
        cmd = "Get-Tpm | Select-Object TpmPresent,TpmReady,TpmEnabled,ManufacturerVersion | ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-Tpm failed (module may be unavailable on this build)"}
        try:
            info = json.loads(result["stdout"]) if result["stdout"] else {}
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "tpm_status": info}

    def get_firmware_summary(self) -> Dict:
        """Convenience: BIOS info + firmware type + Secure Boot + TPM in one call."""
        return {
            "success": True,
            "bios": self.get_bios_info(),
            "firmware_type": self.get_firmware_type(),
            "secure_boot": self.get_secure_boot_status(),
            "tpm": self.get_tpm_status(),
        }

    def restart_to_firmware_settings(self, confirm: bool = False) -> Dict:
        """Reboot straight into the UEFI firmware setup screen. UEFI-only
        (legacy BIOS machines: this either does nothing or performs a
        normal reboot - there is no OS-level way to jump into a legacy
        BIOS menu). Interrupts the user's session immediately, so this
        is confirm-gated like every other reboot tool in this codebase."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would reboot the machine immediately into UEFI firmware settings "
                "(no effect / normal reboot on legacy BIOS machines).",
                "message": "Call again with confirm=true only once the user has explicitly agreed.",
            }
        try:
            result = subprocess.run(
                ["shutdown", "/r", "/fw", "/t", "0"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "shutdown /r /fw failed"}
            return {"success": True, "note": "Reboot to firmware settings initiated."}
        except FileNotFoundError:
            return {"error": "shutdown.exe not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}
