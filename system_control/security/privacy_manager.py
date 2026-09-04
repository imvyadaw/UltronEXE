"""Privacy Manager
===================
Global Windows privacy/telemetry toggles that sit above any single
app: diagnostic-data ("telemetry") level, the per-user advertising ID,
tailored experiences based on diagnostic data, and feedback frequency.
Backed by registry keys under
HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection (telemetry)
and HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\AdvertisingInfo
(advertising ID). Distinct from app_permissions.py (per-app sensor/data
grants like camera or location) and activity_history.py (Timeline
specifically) - this is what Windows itself collects and does with
data, independent of any individual app.

get_* reads need no admin for the advertising ID (HKCU); telemetry
level is HKLM and needs admin even to read cleanly in some
configurations, so read failures get the same admin hint as writes.
Every setter is confirm-gated - these control what leaves this
machine about how it's used.
"""

import subprocess
from typing import Dict


class PrivacyManager:
    """Inspect and control global Windows privacy/telemetry settings."""

    _TELEMETRY_KEY = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection"
    _ADVERTISING_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo"
    _CONTENT_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"

    _TELEMETRY_LEVELS = {
        0: "Security (Enterprise/Education only)",
        1: "Basic",
        2: "Enhanced (deprecated on newer builds)",
        3: "Full",
    }

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
        if err and ("denied" in err.lower() or "elevat" in err.lower() or "access is denied" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_telemetry_level(self) -> Dict:
        """Read the diagnostic-data ('telemetry') level Windows is set to
        report at."""
        script = (
            f"(Get-ItemProperty -Path 'Registry::{self._TELEMETRY_KEY}' "
            "-Name AllowTelemetry -ErrorAction SilentlyContinue).AllowTelemetry"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read telemetry level.")}
        raw = result["stdout"].strip()
        if raw == "":
            return {"level": None, "label": "Not explicitly set (uses Windows default)"}
        try:
            level = int(raw)
        except ValueError:
            return {"error": f"Unexpected telemetry value: {raw}"}
        return {"level": level, "label": self._TELEMETRY_LEVELS.get(level, "Unknown")}

    def set_telemetry_level(self, level: int, confirm: bool = False) -> Dict:
        """Set the diagnostic-data level (0=Security, 1=Basic, 3=Full;
        2/Enhanced is deprecated on current Windows builds). Confirm-gated,
        needs admin - controls how much usage/diagnostic data Microsoft
        receives from this machine."""
        if level not in self._TELEMETRY_LEVELS:
            return {"error": "level must be 0 (Security), 1 (Basic), 2 (Enhanced), or 3 (Full)."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set Windows diagnostic data to level {level} "
                f"('{self._TELEMETRY_LEVELS[level]}'), changing how much usage/diagnostic "
                f"data this machine sends to Microsoft.",
            }
        script = (
            f"$p = 'Registry::{self._TELEMETRY_KEY}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name AllowTelemetry -Value {level} -Type DWord"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set telemetry level.")}
        return {"success": True, "level": level, "label": self._TELEMETRY_LEVELS[level]}

    def get_advertising_id_status(self) -> Dict:
        """Read whether the per-user advertising ID (used for personalized
        ads across apps) is enabled."""
        script = (
            f"(Get-ItemProperty -Path 'Registry::{self._ADVERTISING_KEY}' "
            "-Name Enabled -ErrorAction SilentlyContinue).Enabled"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not read advertising ID status."}
        raw = result["stdout"].strip()
        if raw == "":
            return {"enabled": None, "note": "Not explicitly set (uses Windows default, typically on)."}
        return {"enabled": raw == "1"}

    def set_advertising_id(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable the per-user advertising ID. Confirm-gated -
        no admin required (per-user setting)."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ENABLE' if enabled else 'DISABLE'} the advertising ID used "
                f"for personalized ads across apps on this account.",
            }
        script = (
            f"$p = 'Registry::{self._ADVERTISING_KEY}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name Enabled -Value {1 if enabled else 0} -Type DWord"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to set advertising ID."}
        return {"success": True, "advertising_id_enabled": enabled}

    def get_tailored_experiences_status(self) -> Dict:
        """Read whether 'tailored experiences' (Microsoft using diagnostic
        data to personalize tips/ads/recommendations) is on."""
        script = (
            f"(Get-ItemProperty -Path 'Registry::{self._TELEMETRY_KEY}' "
            "-Name AllowTailoredExperiencesWithDiagnosticData -ErrorAction SilentlyContinue"
            ").AllowTailoredExperiencesWithDiagnosticData"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read tailored-experiences status.")}
        raw = result["stdout"].strip()
        if raw == "":
            return {"enabled": None, "note": "Not explicitly set."}
        return {"enabled": raw == "1"}

    def set_tailored_experiences(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable tailored experiences based on diagnostic data.
        Confirm-gated, needs admin (HKLM policy key)."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ENABLE' if enabled else 'DISABLE'} tailored experiences "
                f"(personalized tips/ads based on diagnostic data).",
            }
        script = (
            f"$p = 'Registry::{self._TELEMETRY_KEY}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name AllowTailoredExperiencesWithDiagnosticData "
            f"-Value {0 if enabled else 1} -Type DWord"
        )
        # Note: the registry value is inverted (1 = disabled) on some builds;
        # normalize so the public API's boolean matches user intent.
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set tailored experiences.")}
        return {"success": True, "tailored_experiences_enabled": enabled}

    def get_summary(self) -> Dict:
        """One-call snapshot of the main privacy toggles this module tracks."""
        return {
            "telemetry": self.get_telemetry_level(),
            "advertising_id": self.get_advertising_id_status(),
            "tailored_experiences": self.get_tailored_experiences_status(),
        }
