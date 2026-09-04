"""Camera Control
================
Device-level webcam management - distinct from every other camera-
adjacent module already in the codebase:

- skills/vision/camera_manager.py, eyes/live_camera.py - actually
  *capturing frames* from the camera for ULTRON's own vision features
  (OpenCV/frame grab). This module never opens a frame; it only
  enumerates/enables/disables the device and reports usage.
- system_control/security/app_permissions.py - the OS-wide and per-app
  privacy *consent* toggle ("Allow apps to access your camera" and
  each app's own Allow/Deny). That governs whether an app is permitted
  to ask for the camera; this module governs whether the camera
  *device itself* is present and enabled at all, one level below
  consent.
- system_control/system_config/device_manager.py - generic PnP
  enable/disable for any device class. This module is a thin,
  camera-scoped convenience over the same Enable-PnpDevice/
  Disable-PnpDevice cmdlets, plus camera-specific reads that generic
  device management doesn't provide (in-use detection).

In-use detection reads the same per-capability usage timestamps
Windows itself uses to light up the camera-in-use indicator in the
system tray: HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\
CapabilityAccessManager\\ConsentStore\\webcam(\\NonPackaged)\\<app>,
where a LastUsedTimeStop of 0 means that app is *currently* using the
camera. No admin needed to read.

Disabling the camera device is confirm-gated and needs admin - it
affects every app on the machine, not just one, until re-enabled.
"""

import subprocess
import winreg
from typing import Dict

_CONSENT_BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"


class CameraControl:
    """Enumerate, enable/disable, and check current usage of webcam
    devices, distinct from actually capturing frames from one."""

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

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "elevat" in err.lower()):
            return err + " - run ULTRON as Administrator."
        return err

    def list_cameras(self) -> Dict:
        """All currently-known camera/imaging devices: friendly name,
        InstanceId, and enabled/disabled status. Use InstanceId with
        set_camera_enabled() below. No admin needed."""
        result = self._run_ps(
            "Get-PnpDevice -Class Camera, Image -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        if not result["stdout"]:
            return {"success": True, "cameras": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse camera list"}
        cameras = data if isinstance(data, list) else [data]
        return {"success": True, "cameras": cameras, "count": len(cameras)}

    def set_camera_enabled(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable a camera device by InstanceId (from
        list_cameras). Confirm-gated - disabling cuts off every app's
        access to that camera, not just one, until re-enabled. Needs
        admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} camera device {instance_id} for every app on this machine.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        result = self._run_ps(f"{verb} -InstanceId '{safe_id}' -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {action} camera")}
        return {"success": True, "instance_id": instance_id, "enabled": enabled}

    def get_camera_privacy_status(self) -> Dict:
        """The machine-wide 'Allow apps to access your camera' switch,
        read directly (a read-only convenience mirror of what
        security/app_permissions.py's get_global_status('camera')
        already exposes - use that module to change it). No admin
        needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CONSENT_BASE) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "Value")
                    return {"allowed": value == "Allow", "raw_value": value}
                except FileNotFoundError:
                    return {"allowed": None, "raw_value": "NotSet"}
        except FileNotFoundError:
            return {"allowed": None, "raw_value": "NotSet"}
        except OSError as e:
            return {"error": str(e)}

    def get_apps_using_camera(self) -> Dict:
        """Which apps currently have the camera open right now (not
        just granted access) - LastUsedTimeStop == 0 means still in
        use. The same source Windows reads to light up the camera-
        in-use tray indicator. No admin needed."""
        result = self._run_ps(
            f"$p = 'Registry::HKLM\\{_CONSENT_BASE}\\NonPackaged'; "
            "if (Test-Path $p) { Get-ChildItem -Path $p | ForEach-Object { "
            "[PSCustomObject]@{ App = $_.PSChildName; "
            "LastUsedTimeStop = (Get-ItemProperty -Path $_.PSPath -Name LastUsedTimeStop -ErrorAction SilentlyContinue).LastUsedTimeStop } "
            "} | ConvertTo-Json } else { '[]' }"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Could not read camera usage")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
        except Exception:
            return {"error": "Could not parse camera usage", "raw": result["stdout"]}
        in_use = [d.get("App") for d in data if d.get("LastUsedTimeStop") == 0]
        return {"success": True, "apps_using_camera": in_use, "in_use": len(in_use) > 0}
