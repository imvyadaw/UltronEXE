"""App Permissions Manager
===========================
Windows' per-app privacy permissions (Settings > Privacy & security >
App permissions) - camera, microphone, location, contacts, calendar,
etc. Backed by the registry under HKCU/HKLM
\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\
ConsentStore\\<capability>, where each app has its own subkey holding
an "Allow"/"Deny" string. Distinct from privacy_manager.py (global OS
telemetry/advertising-ID/diagnostic-data toggles, not per-app grants)
and from activity_history.py (Timeline-specific) - this module is
specifically "which apps can use which sensors/data categories".

Listing capabilities and per-app/global status are plain reads. Every
setter (global allow/deny for a capability, or a single app's access)
is confirm-gated - these directly control what installed apps, some
of which may not be trustworthy, can see and record about the user.
"""

import subprocess
from typing import Dict, Optional


class AppPermissionsManager:
    """Inspect and control Windows per-app privacy capability grants."""

    _BASE = r"HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"

    # Friendly name -> registry capability subkey name.
    _CAPABILITIES = {
        "camera": "webcam",
        "microphone": "microphone",
        "location": "location",
        "contacts": "contacts",
        "calendar": "appointments",
        "call_history": "phoneCallHistory",
        "email": "email",
        "messaging": "chat",
        "camera_video": "videos",
        "documents": "documentsLibrary",
        "pictures": "picturesLibrary",
        "screen_activity": "graphicsCaptureProgrammatic",
        "notifications": "userNotificationListener",
        "bluetooth": "bluetoothSync",
        "accessory_devices": "radios",
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

    def list_capabilities(self) -> Dict:
        """List the recognized privacy capability categories this module
        can inspect/control (camera, microphone, location, etc.)."""
        return {"capabilities": sorted(self._CAPABILITIES.keys())}

    def _resolve(self, capability: str) -> Optional[str]:
        return self._CAPABILITIES.get(capability.lower().replace(" ", "_"))

    def get_global_status(self, capability: str) -> Dict:
        """Get the machine-wide toggle for a capability (the top-level
        'Allow apps to access your <capability>' switch), plus whether
        any per-app overrides exist under it."""
        key = self._resolve(capability)
        if not key:
            return {"error": f"Unknown capability '{capability}'. Call list_capabilities() for valid names."}
        script = (
            f"$p = 'Registry::{self._BASE}\\{key}'; "
            "if (Test-Path $p) { (Get-ItemProperty -Path $p -Name Value -ErrorAction SilentlyContinue).Value } "
            "else { 'NotSet' }"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read capability status.")}
        value = result["stdout"].strip()
        return {
            "capability": capability,
            "allowed": value == "Allow" if value in ("Allow", "Deny") else None,
            "raw_value": value,
        }

    def list_app_access(self, capability: str) -> Dict:
        """List every app with a recorded Allow/Deny entry for a capability,
        and its individual grant."""
        key = self._resolve(capability)
        if not key:
            return {"error": f"Unknown capability '{capability}'. Call list_capabilities() for valid names."}
        script = (
            f"$p = 'Registry::{self._BASE}\\{key}'; "
            "if (Test-Path $p) { "
            "Get-ChildItem -Path $p | ForEach-Object { "
            "[PSCustomObject]@{ App = $_.PSChildName; Value = (Get-ItemProperty -Path $_.PSPath -Name Value -ErrorAction SilentlyContinue).Value } "
            "} | ConvertTo-Json } else { '[]' }"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not list per-app access.")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
        except Exception:
            return {"error": "Could not parse per-app access list.", "raw": result["stdout"]}
        apps = [{"app": a.get("App"), "allowed": a.get("Value") == "Allow"} for a in data if a.get("App")]
        return {"capability": capability, "apps": apps, "count": len(apps)}

    def set_global_access(self, capability: str, allowed: bool, confirm: bool = False) -> Dict:
        """Turn a capability on/off machine-wide for ALL apps (the top-level
        privacy switch). Confirm-gated, needs admin - this can silently cut
        off every app's access to a sensor or data category at once."""
        key = self._resolve(capability)
        if not key:
            return {"error": f"Unknown capability '{capability}'. Call list_capabilities() for valid names."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ALLOW' if allowed else 'BLOCK'} ALL apps from accessing {capability}, machine-wide.",
            }
        value = "Allow" if allowed else "Deny"
        script = (
            f"$p = 'Registry::{self._BASE}\\{key}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name Value -Value '{value}' -Type String"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set global capability access.")}
        return {"success": True, "capability": capability, "allowed": allowed}

    def set_app_access(self, capability: str, app_name: str, allowed: bool, confirm: bool = False) -> Dict:
        """Grant or revoke a single app's access to a capability. app_name
        must match the app's registry subkey name (from list_app_access()).
        Confirm-gated - directly controls what a specific, possibly
        untrusted app can see."""
        key = self._resolve(capability)
        if not key:
            return {"error": f"Unknown capability '{capability}'. Call list_capabilities() for valid names."}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ALLOW' if allowed else 'BLOCK'} '{app_name}' from accessing {capability}.",
            }
        value = "Allow" if allowed else "Deny"
        safe_app = app_name.replace("'", "''")
        script = (
            f"$p = 'Registry::{self._BASE}\\{key}\\{safe_app}'; "
            f"if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}; "
            f"Set-ItemProperty -Path $p -Name Value -Value '{value}' -Type String"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Failed to set per-app capability access.")}
        return {"success": True, "capability": capability, "app": app_name, "allowed": allowed}
