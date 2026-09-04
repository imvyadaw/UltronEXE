"""Speaker Control
=================
Device-level audio-output management - distinct from every other
speaker/volume-adjacent module already in the codebase:

- windows/audio/volume.py - master volume/mute of whichever device is
  currently DEFAULT only. This module targets a specific output
  device by id (default or not).
- system_control/ui/sound_manager.py - already owns listing playback
  devices, switching the DEFAULT one, per-*application* volume (the
  mixer), and sound schemes. This module does not duplicate any of
  that; it fills the one gap left - a specific device's own volume/
  mute regardless of which one is default - and adds physical
  enable/disable and a test tone, neither of which sound_manager.py
  or volume.py cover.

Per-device volume/mute uses pycaw's IAudioEndpointVolume targeted at
a chosen render endpoint (AudioUtilities.GetAllDevices()), the same
approach microphone_control.py uses on the capture side. Enable/
disable is the underlying PnP device.

Volume/mute changes are per-user convenience settings and are NOT
confirm-gated. Disabling the physical output device is confirm-gated
and needs admin - it silences that device for every app, not just
one, until re-enabled.
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

try:
    import winsound

    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


class SpeakerControl:
    """Per-device speaker/output volume, mute, physical enable/
    disable, and a test tone - distinct from master-volume and
    default-device selection, both owned elsewhere."""

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

    def _get_render_endpoint(self, device_id: Optional[str] = None):
        """Return the pycaw AudioDevice for a render endpoint - the
        given device_id, or the default playback device if omitted."""
        if device_id:
            for dev in AudioUtilities.GetAllDevices():
                if getattr(dev, "id", None) == device_id:
                    return dev
            return None
        return AudioUtilities.GetSpeakers()

    def _volume_interface(self, dev):
        interface = getattr(dev, "EndpointVolume", None)
        if interface is not None:
            return interface
        return cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))

    def list_speakers(self) -> Dict:
        """All currently-known playback (render) endpoints: id, name,
        and whether each is the system default. No admin needed."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            default_id = None
            try:
                default_id = AudioUtilities.GetSpeakers().id
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
            speakers: List[Dict] = []
            for dev in AudioUtilities.GetAllDevices():
                name = getattr(dev, "FriendlyName", None) or str(dev)
                dev_id = getattr(dev, "id", None)
                is_default = dev_id == default_id
                # Same render-vs-capture disambiguation heuristic as
                # microphone_control.py's list_microphones(), mirrored.
                if not is_default and ("microphone" in name.lower() or name.lower().strip() == "mic"):
                    continue
                speakers.append({"id": dev_id, "name": name, "is_default": is_default})
            return {"success": True, "speakers": speakers, "count": len(speakers)}
        except Exception as e:
            return {"error": str(e)}

    def get_device_volume(self, device_id: Optional[str] = None) -> Dict:
        """Current volume (0-100) for a specific output device
        (default if device_id omitted). No admin needed."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            dev = self._get_render_endpoint(device_id)
            if dev is None:
                return {"error": f"No speaker found for device_id '{device_id}'"}
            return {"success": True, "volume": round(self._volume_interface(dev).GetMasterVolumeLevelScalar() * 100)}
        except Exception as e:
            return {"error": str(e)}

    def set_device_volume(self, level: int, device_id: Optional[str] = None) -> Dict:
        """Set volume (0-100) for a specific output device (default if
        device_id omitted). Not confirm-gated."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            level = max(0, min(100, level))
            dev = self._get_render_endpoint(device_id)
            if dev is None:
                return {"error": f"No speaker found for device_id '{device_id}'"}
            self._volume_interface(dev).SetMasterVolumeLevelScalar(level / 100, None)
            return {"success": True, "volume": level}
        except Exception as e:
            return {"error": str(e)}

    def get_device_mute(self, device_id: Optional[str] = None) -> Dict:
        """Whether a specific output device is muted. No admin
        needed."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            dev = self._get_render_endpoint(device_id)
            if dev is None:
                return {"error": f"No speaker found for device_id '{device_id}'"}
            return {"success": True, "muted": bool(self._volume_interface(dev).GetMute())}
        except Exception as e:
            return {"error": str(e)}

    def set_device_mute(self, muted: bool, device_id: Optional[str] = None) -> Dict:
        """Mute/unmute a specific output device. Not confirm-gated."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            dev = self._get_render_endpoint(device_id)
            if dev is None:
                return {"error": f"No speaker found for device_id '{device_id}'"}
            self._volume_interface(dev).SetMute(1 if muted else 0, None)
            return {"success": True, "muted": muted}
        except Exception as e:
            return {"error": str(e)}

    def play_test_tone(self) -> Dict:
        """Play a short beep on the current DEFAULT output device, the
        same purpose as the 'Test' button in Settings > Sound. Only
        the default device is reachable this way without a full audio
        playback stack - to test a non-default device, switch it to
        default first via sound_manager.py."""
        if not HAS_WINSOUND:
            return {"error": "winsound not available - this is only available on Windows"}
        try:
            winsound.Beep(880, 400)
            return {"success": True, "played": True}
        except RuntimeError as e:
            return {"error": f"{e} - winsound.Beep only works on the default output device"}
        except Exception as e:
            return {"error": str(e)}

    def list_speaker_devices_pnp(self) -> Dict:
        """The underlying PnP audio-output hardware (as opposed to the
        Windows audio *endpoint*, above) - use this InstanceId with
        set_speaker_enabled(). No admin needed."""
        result = self._run_ps(
            "Get-PnpDevice -Class AudioEndpoint, Media -ErrorAction SilentlyContinue | "
            "Where-Object { $_.FriendlyName -notmatch 'microphone|mic array' } | "
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

    def set_speaker_enabled(self, instance_id: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable an output device's underlying PnP device
        (from list_speaker_devices_pnp). Confirm-gated - silences that
        device for every app, not just one. Needs admin."""
        if not instance_id:
            return {"error": "instance_id must be non-empty"}
        action = "enable" if enabled else "disable"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} speaker device {instance_id} for every app on this machine.",
            }
        safe_id = instance_id.replace("'", "''")
        verb = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
        result = self._run_ps(f"{verb} -InstanceId '{safe_id}' -Confirm:$false")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or f"Could not {action} speaker")}
        return {"success": True, "instance_id": instance_id, "enabled": enabled}
