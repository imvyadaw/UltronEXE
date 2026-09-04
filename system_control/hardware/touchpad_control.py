"""Touchpad Control
==================
Laptop touchpad management - not covered by any other module in the
codebase. mouse_control.py and cursor_manager.py both apply to
pointing devices in general (button swap, wheel lines, pointer speed/
appearance) but neither touches touchpad-specific concerns: gestures,
tap-to-click, palm rejection, or the physical presence of a touchpad
at all (desktops have none).

Precision Touchpad settings (the modern driver-agnostic stack every
current laptop uses, superseding vendor-specific Synaptics/ELAN
control panels) live under HKCU\\Software\\Microsoft\\Windows\\
CurrentVersion\\PrecisionTouchPad - the same values Settings > Bluetooth
& devices > Touchpad reads and writes. The physical device itself is
enumerated/enabled/disabled the same PnP way as every other hardware/
*.py module (Mouse/HIDClass, matching common touchpad vendor names in
FriendlyName).

Gesture/sensitivity settings are per-user convenience preferences,
same class as cursor_manager.py's - not confirm-gated. Disabling the
physical touchpad device is confirm-gated and needs admin - on a
laptop with no other pointing device attached this can leave the
machine hard to control until re-enabled or a mouse is plugged in.
"""

import subprocess
import winreg
from typing import Dict, Optional

_PTP_PATH = r"Software\Microsoft\Windows\CurrentVersion\PrecisionTouchPad"

# Friendly-name substrings covering the touchpad vendors Windows PnP
# reports under Class Mouse/HIDClass - there is no dedicated "Touchpad"
# PnP class, so this is the same kind of name-matching heuristic
# microphone_control.py/speaker_control.py use to tell endpoints apart.
_TOUCHPAD_NAME_HINTS = ("touchpad", "touch pad", "glidepoint", "synaptics", "elan", "precision touchpad")

# PrecisionTouchPad registry value name -> (friendly key, is bool)
_GESTURE_SETTINGS = {
    "TapsEnabled": ("tap_to_click", True),
    "TapAndDragEnabled": ("tap_and_drag", True),
    "PanEnabled": ("two_finger_scroll", True),
    "ZoomEnabled": ("pinch_to_zoom", True),
    "RightClickZoneEnabled": ("two_finger_right_click", True),
    "ThreeFingerSlideEnabled": ("three_finger_swipe", True),
    "ThreeFingerTapEnabled": ("three_finger_tap", True),
    "FourFingerSlideEnabled": ("four_finger_swipe", True),
    "FourFingerTapEnabled": ("four_finger_tap", True),
}


class TouchpadControl:
    """Physical touchpad device enable/disable plus Precision Touchpad
    gesture/sensitivity settings - the one hardware/*.py category with
    no prior coverage anywhere else in the codebase."""

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

    def list_touchpads(self) -> Dict:
        """Currently-known touchpad devices, found by matching known
        vendor/name hints against Mouse and HIDClass PnP entries
        (there is no dedicated 'Touchpad' PnP class). Use InstanceId
        with set_touchpad_enabled() below. No admin needed. Returns an
        empty list on a desktop with no touchpad."""
        result = self._run_ps(
            "Get-PnpDevice -Class Mouse, HIDClass -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-PnpDevice failed"}
        if not result["stdout"]:
            return {"success": True, "touchpads": [], "count": 0}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse device list"}
        devices = data if isinstance(data, list) else [data]
        touchpads = [
            d for d in devices if any(hint in (d.get("FriendlyName") or "").lower() for hint in _TOUCHPAD_NAME_HINTS)
        ]
        return {"success": True, "touchpads": touchpads, "count": len(touchpads)}

    def set_touchpad_enabled(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable a touchpad device by InstanceId (from
        list_touchpads). Confirm-gated - on a laptop with no other
        pointing device attached, disabling leaves the machine hard to
        control until re-enabled or a mouse is plugged in. Needs
        admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} touchpad device {instance_id}. "
                f"If no other pointing device is attached, disabling leaves the machine hard to control.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        result = self._run_ps(f"{verb} -InstanceId '{safe_id}' -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {action} touchpad")}
        return {"success": True, "instance_id": instance_id, "enabled": enabled}

    def get_gesture_settings(self) -> Dict:
        """Current Precision Touchpad gesture toggles (tap-to-click,
        tap-and-drag, two/three/four-finger gestures, pinch-to-zoom) -
        Settings > Bluetooth & devices > Touchpad. No admin needed.
        Missing values default to enabled, matching Windows' own
        behavior when a key is absent."""
        settings: Dict = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PTP_PATH) as key:
                for reg_name, (friendly, _is_bool) in _GESTURE_SETTINGS.items():
                    try:
                        value, _ = winreg.QueryValueEx(key, reg_name)
                        settings[friendly] = bool(value)
                    except FileNotFoundError:
                        settings[friendly] = True
            return {"success": True, "settings": settings}
        except FileNotFoundError:
            # Key doesn't exist yet - this device has never had these customized,
            # meaning every gesture is still at its Windows-default of enabled.
            return {"success": True, "settings": {friendly: True for friendly, _ in _GESTURE_SETTINGS.values()}}
        except OSError as e:
            return {"error": str(e)}

    def set_gesture_setting(self, setting: str, enabled: bool) -> Dict:
        """Turn one Precision Touchpad gesture on/off, by friendly name
        (see get_gesture_settings() for the full list, e.g.
        'tap_to_click', 'two_finger_scroll'). Not confirm-gated - a
        per-user convenience preference, reversible any time."""
        reg_name = next((k for k, (friendly, _) in _GESTURE_SETTINGS.items() if friendly == setting), None)
        if reg_name is None:
            return {"error": f"Unknown setting '{setting}'. Valid: {sorted(f for f, _ in _GESTURE_SETTINGS.values())}"}
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _PTP_PATH) as key:
                winreg.SetValueEx(key, reg_name, 0, winreg.REG_DWORD, 1 if enabled else 0)
            return {"success": True, "setting": setting, "enabled": enabled}
        except OSError as e:
            return {"error": str(e)}

    def get_sensitivity(self) -> Dict:
        """Current touchpad cursor speed (CursorSpeed, roughly 0-20)
        and click-force sensitivity for force-touch trackpads
        (ClickForceSensitivity, roughly 0-3), where present. No admin
        needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PTP_PATH) as key:
                result: Dict = {"success": True}
                try:
                    cursor_speed, _ = winreg.QueryValueEx(key, "CursorSpeed")
                    result["cursor_speed"] = int(cursor_speed)
                except FileNotFoundError:
                    result["cursor_speed"] = None
                try:
                    click_force, _ = winreg.QueryValueEx(key, "ClickForceSensitivity")
                    result["click_force_sensitivity"] = int(click_force)
                except FileNotFoundError:
                    result["click_force_sensitivity"] = None
                return result
        except FileNotFoundError:
            return {"success": True, "cursor_speed": None, "click_force_sensitivity": None}
        except OSError as e:
            return {"error": str(e)}

    def set_sensitivity(
        self, cursor_speed: Optional[int] = None, click_force_sensitivity: Optional[int] = None
    ) -> Dict:
        """Set touchpad cursor speed (0-20) and/or click-force
        sensitivity (0-3, only meaningful on force-touch trackpads).
        Not confirm-gated."""
        if cursor_speed is None and click_force_sensitivity is None:
            return {"error": "Provide at least one of cursor_speed or click_force_sensitivity"}
        result: Dict = {"success": True}
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _PTP_PATH) as key:
                if cursor_speed is not None:
                    cursor_speed = max(0, min(20, int(cursor_speed)))
                    winreg.SetValueEx(key, "CursorSpeed", 0, winreg.REG_DWORD, cursor_speed)
                    result["cursor_speed"] = cursor_speed
                if click_force_sensitivity is not None:
                    click_force_sensitivity = max(0, min(3, int(click_force_sensitivity)))
                    winreg.SetValueEx(key, "ClickForceSensitivity", 0, winreg.REG_DWORD, click_force_sensitivity)
                    result["click_force_sensitivity"] = click_force_sensitivity
            return result
        except OSError as e:
            return {"error": str(e)}
