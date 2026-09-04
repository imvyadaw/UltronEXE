"""Microphone Control
====================
Device-level microphone management - distinct from every other
microphone-adjacent module already in the codebase:

- voice/microphone/microphone.py, voice/microphone/stream.py - actually
  *capturing audio* from whichever mic is already default, for STT.
  This module never records anything.
- system_control/ui/sound_manager.py - already owns listing recording
  devices and switching which one is the system DEFAULT. This module
  does not duplicate that; instead it operates on a specific device
  BY ID (default or not): its own mute state, its own input volume/
  gain, and whether the underlying hardware device is enabled at all.
- system_control/security/app_permissions.py - the OS-wide/per-app
  privacy *consent* toggle ("Allow apps to access your microphone").
  That's permission; this module is the physical device one level
  below permission.

Per-device mute/volume goes through pycaw's IAudioEndpointVolume
targeted at a specific capture endpoint (not just the default one, via
AudioUtilities.GetAllDevices() filtered to the eCapture data-flow),
mirroring how sound_manager.py already reaches per-app sessions on the
render side. Enable/disable is the PnP device itself.

Mute/volume changes are per-user convenience settings and are NOT
confirm-gated (same class as sound_manager.py's per-app volume).
Disabling the physical device is confirm-gated and needs admin - like
camera_control.py, it cuts off every app at once, not just one.
"""
import logging

import subprocess
from typing import Dict, List, Optional

try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

_CONSENT_BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"


class MicrophoneControl:
    """Per-device microphone mute/volume, physical enable/disable, and
    current-usage checks - distinct from the STT capture pipeline and
    from default-device selection, both owned elsewhere."""

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

    def _get_capture_endpoint(self, device_id: Optional[str] = None):
        """Return the pycaw AudioDevice for a capture endpoint - the
        given device_id, or the default recording device if omitted."""
        if device_id:
            for dev in AudioUtilities.GetAllDevices():
                if getattr(dev, "id", None) == device_id:
                    return dev
            return None
        return AudioUtilities.GetMicrophone()

    def list_microphones(self) -> Dict:
        """All currently-known recording (capture) endpoints: id,
        name, and whether each is the system default. No admin
        needed."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            default_id = None
            try:
                default_id = AudioUtilities.GetMicrophone().id
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
            # GetAllDevices() mixes render + capture; pycaw's AudioDevice wrapper
            # doesn't expose data-flow directly, so capture endpoints are identified
            # by FriendlyName heuristics plus cross-checking GetMicrophone()'s id -
            # good enough to disambiguate for a caller picking a device_id, without
            # pulling in a raw IMMDeviceEnumerator/EDataFlow.eCapture COM call.
            mics: List[Dict] = []
            for dev in AudioUtilities.GetAllDevices():
                name = getattr(dev, "FriendlyName", None) or str(dev)
                dev_id = getattr(dev, "id", None)
                is_default = dev_id == default_id
                if not is_default and "microphone" not in name.lower() and "mic" not in name.lower():
                    continue
                mics.append({"id": dev_id, "name": name, "is_default": is_default})
            return {"success": True, "microphones": mics, "count": len(mics)}
        except Exception as e:
            return {"error": str(e)}

    def get_mic_mute(self, device_id: Optional[str] = None) -> Dict:
        """Whether a microphone (default, or a specific device_id from
        list_microphones) is currently muted. No admin needed."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            dev = self._get_capture_endpoint(device_id)
            if dev is None:
                return {"error": f"No microphone found for device_id '{device_id}'"}
            interface = dev.EndpointVolume if hasattr(dev, "EndpointVolume") else None
            if interface is None:
                interface = cast(
                    dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume)
                )
            return {"success": True, "muted": bool(interface.GetMute())}
        except Exception as e:
            return {"error": str(e)}

    def set_mic_mute(self, muted: bool, device_id: Optional[str] = None) -> Dict:
        """Mute/unmute a microphone (default, or a specific device_id).
        Not confirm-gated - same class as volume, a reversible one-user
        convenience setting."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            dev = self._get_capture_endpoint(device_id)
            if dev is None:
                return {"error": f"No microphone found for device_id '{device_id}'"}
            interface = dev.EndpointVolume if hasattr(dev, "EndpointVolume") else None
            if interface is None:
                interface = cast(
                    dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume)
                )
            interface.SetMute(1 if muted else 0, None)
            return {"success": True, "muted": muted}
        except Exception as e:
            return {"error": str(e)}

    def get_mic_volume(self, device_id: Optional[str] = None) -> Dict:
        """Current input volume/gain (0-100) for a microphone. No
        admin needed."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            dev = self._get_capture_endpoint(device_id)
            if dev is None:
                return {"error": f"No microphone found for device_id '{device_id}'"}
            interface = dev.EndpointVolume if hasattr(dev, "EndpointVolume") else None
            if interface is None:
                interface = cast(
                    dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume)
                )
            return {"success": True, "volume": round(interface.GetMasterVolumeLevelScalar() * 100)}
        except Exception as e:
            return {"error": str(e)}

    def set_mic_volume(self, level: int, device_id: Optional[str] = None) -> Dict:
        """Set input volume/gain (0-100) for a microphone. Not
        confirm-gated."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            level = max(0, min(100, level))
            dev = self._get_capture_endpoint(device_id)
            if dev is None:
                return {"error": f"No microphone found for device_id '{device_id}'"}
            interface = dev.EndpointVolume if hasattr(dev, "EndpointVolume") else None
            if interface is None:
                interface = cast(
                    dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume)
                )
            interface.SetMasterVolumeLevelScalar(level / 100, None)
            return {"success": True, "volume": level}
        except Exception as e:
            return {"error": str(e)}

    def list_mic_devices_pnp(self) -> Dict:
        """The underlying PnP audio-input hardware (as opposed to the
        Windows audio *endpoint*, above) - use this InstanceId with
        set_mic_enabled(). No admin needed."""
        result = self._run_ps(
            "Get-PnpDevice -Class AudioEndpoint, Media -ErrorAction SilentlyContinue | "
            "Where-Object { $_.FriendlyName -match 'microphone|mic array|mic\\b' } | "
            "Select-Object FriendlyName, InstanceId, Status | ConvertTo-Json"
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

    def set_mic_enabled(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable a microphone's underlying PnP device (from
        list_mic_devices_pnp). Confirm-gated - cuts off every app's
        access to that mic, not just one. Needs admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} microphone device {instance_id} for every app on this machine.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        result = self._run_ps(f"{verb} -InstanceId '{safe_id}' -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {action} microphone")}
        return {"success": True, "instance_id": instance_id, "enabled": enabled}

    def get_apps_using_microphone(self) -> Dict:
        """Which apps currently have the microphone open right now -
        same LastUsedTimeStop==0 mechanism as camera_control.py's
        get_apps_using_camera(). No admin needed."""
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
            return {"error": self._admin_hint(result["stderr"] or "Could not read microphone usage")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
        except Exception:
            return {"error": "Could not parse microphone usage", "raw": result["stdout"]}
        in_use = [d.get("App") for d in data if d.get("LastUsedTimeStop") == 0]
        return {"success": True, "apps_using_microphone": in_use, "in_use": len(in_use) > 0}
