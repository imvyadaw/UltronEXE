"""Sound Manager
===============
Reads and controls the Windows Sound panel surface that
windows/audio/volume.py's VolumeControl does NOT cover -
windows/audio/volume.py is master-volume/mute only, via pycaw's
IAudioEndpointVolume on the default device. This module adds:
  - Listing playback/recording devices and switching the DEFAULT one
    (Settings > System > Sound > Output/Input) - via the
    AudioDeviceCmdlets PowerShell module (Get-AudioDevice/
    Set-AudioDevice), since pycaw itself has no supported way to change
    the OS default endpoint, only to read/control whichever one is
    already default.
  - Per-application volume (the "Volume mixer" - each running app's own
    slider) via pycaw's ISimpleAudioVolume on each audio session,
    which volume.py never touches (it only touches the master
    endpoint).
  - Sound scheme selection (which .wav plays for system events) via
    the same per-user registry mechanism theme_manager.py uses for
    .theme files.

Distinct from windows/audio/volume.py (master volume, unaffected by
anything here) and skills/vision or media modules (unrelated).

Reading, per-app volume, and sound-scheme changes are per-user
cosmetic/convenience preferences and are NOT confirm-gated. Switching
the default playback/recording DEVICE is more consequential (audio can
suddenly come out of/be captured from a different device entirely,
including unplugging headphones' worth of surprise) - confirm-gated.
"""

import subprocess
from typing import Dict, List

try:
    from ctypes import POINTER, cast
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False


class SoundManager:
    """Device selection, per-app volume mixer, and sound scheme control."""

    _SCHEMES_KEY = r"HKCU\AppEvents\Schemes"

    def _run_ps(self, script: str, timeout: float = 15.0) -> Dict:
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

    def _has_audio_device_cmdlets(self) -> bool:
        result = self._run_ps(
            "Get-Module -ListAvailable -Name AudioDeviceCmdlets | Select-Object -First 1 | ForEach-Object { $_.Name }"
        )
        return result.get("success") and "AudioDeviceCmdlets" in result.get("stdout", "")

    # -- Device listing / default device switching ---------------------------
    def list_playback_devices(self) -> Dict:
        """List playback (output) devices. Needs the AudioDeviceCmdlets
        PowerShell module (Install-Module AudioDeviceCmdlets)."""
        if not self._has_audio_device_cmdlets():
            return {
                "error": "AudioDeviceCmdlets PowerShell module not installed - run: Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser"
            }
        result = self._run_ps(
            "Get-AudioDevice -List | Where-Object { $_.Type -eq 'Playback' } | Select-Object Index,Name,Default | ConvertTo-Json -Compress"
        )
        return self._parse_device_list(result)

    def list_recording_devices(self) -> Dict:
        """List recording (input/microphone) devices. Needs
        AudioDeviceCmdlets."""
        if not self._has_audio_device_cmdlets():
            return {
                "error": "AudioDeviceCmdlets PowerShell module not installed - run: Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser"
            }
        result = self._run_ps(
            "Get-AudioDevice -List | Where-Object { $_.Type -eq 'Recording' } | Select-Object Index,Name,Default | ConvertTo-Json -Compress"
        )
        return self._parse_device_list(result)

    def _parse_device_list(self, result: Dict) -> Dict:
        if "error" in result:
            return result
        if not result.get("success"):
            return {"error": result.get("stderr") or "Failed to list devices."}
        import json

        raw = result.get("stdout", "").strip()
        if not raw:
            return {"devices": [], "count": 0}
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {"error": "Could not parse device list."}
        devices = parsed if isinstance(parsed, list) else [parsed]
        return {"devices": devices, "count": len(devices)}

    def get_default_playback_device(self) -> Dict:
        """Read the current default output device."""
        if not self._has_audio_device_cmdlets():
            return {
                "error": "AudioDeviceCmdlets PowerShell module not installed - run: Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser"
            }
        result = self._run_ps("(Get-AudioDevice -Playback).Name")
        if "error" in result or not result.get("success"):
            return {"error": result.get("stderr") or "Could not read the default playback device."}
        return {"default_playback_device": result["stdout"].strip() or None}

    def set_default_playback_device(self, name_or_index, confirm: bool = False) -> Dict:
        """Switch the default output device by name or list index (from
        list_playback_devices). Confirm-gated - audio suddenly moving to
        a different device (or headphones going silent) is disruptive."""
        return self._set_default_device("Playback", name_or_index, confirm)

    def get_default_recording_device(self) -> Dict:
        """Read the current default input (microphone) device."""
        if not self._has_audio_device_cmdlets():
            return {
                "error": "AudioDeviceCmdlets PowerShell module not installed - run: Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser"
            }
        result = self._run_ps("(Get-AudioDevice -Recording).Name")
        if "error" in result or not result.get("success"):
            return {"error": result.get("stderr") or "Could not read the default recording device."}
        return {"default_recording_device": result["stdout"].strip() or None}

    def set_default_recording_device(self, name_or_index, confirm: bool = False) -> Dict:
        """Switch the default input device by name or list index (from
        list_recording_devices). Confirm-gated - the app that's about
        to start listening (a call, voice command) could suddenly hear
        nothing if switched mid-use."""
        return self._set_default_device("Recording", name_or_index, confirm)

    def _set_default_device(self, kind: str, name_or_index, confirm: bool) -> Dict:
        if not confirm:
            return {
                "error": f"Switching the default {kind.lower()} device changes where audio goes/comes from immediately. Call again with confirm=True to proceed.",
                "requires_confirmation": True,
            }
        if not self._has_audio_device_cmdlets():
            return {
                "error": "AudioDeviceCmdlets PowerShell module not installed - run: Install-Module -Name AudioDeviceCmdlets -Scope CurrentUser"
            }
        if isinstance(name_or_index, int) or str(name_or_index).isdigit():
            script = f"Set-AudioDevice -Index {int(name_or_index)}"
        else:
            escaped = str(name_or_index).replace("'", "''")
            script = f"Set-AudioDevice -ID (Get-AudioDevice -List | Where-Object {{ $_.Type -eq '{kind}' -and $_.Name -like '*{escaped}*' }} | Select-Object -First 1 -ExpandProperty ID)"
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or f"Failed to switch the default {kind.lower()} device."}
        return {"success": True, "device": name_or_index}

    # -- Per-application volume mixer -----------------------------------------
    def _find_sessions(self, app_name: str) -> List:
        sessions = AudioUtilities.GetAllSessions()
        needle = app_name.lower().strip()
        return [s for s in sessions if s.Process and needle in s.Process.name().lower()]

    def list_app_sessions(self) -> Dict:
        """List running apps that currently have an audio session (i.e.
        would show up in the Volume Mixer), with their current volume
        and mute state."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            sessions = AudioUtilities.GetAllSessions()
            apps = []
            for s in sessions:
                if not s.Process:
                    continue
                volume = (
                    cast(s.SimpleAudioVolume, POINTER(ISimpleAudioVolume)) if hasattr(s, "SimpleAudioVolume") else None
                )
                vol_iface = s._ctl.QueryInterface(ISimpleAudioVolume) if volume is None else volume
                apps.append(
                    {
                        "process_name": s.Process.name(),
                        "pid": s.Process.pid,
                        "volume_percent": round(vol_iface.GetMasterVolume() * 100),
                        "muted": bool(vol_iface.GetMute()),
                    }
                )
            return {"apps": apps, "count": len(apps)}
        except Exception as e:
            return {"error": str(e)}

    def get_app_volume(self, app_name: str) -> Dict:
        """Read a specific app's mixer volume by process name (e.g.
        'chrome', 'spotify' - partial, case-insensitive match)."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            matches = self._find_sessions(app_name)
            if not matches:
                return {"error": f"No running app with an audio session matching '{app_name}'."}
            s = matches[0]
            vol_iface = s._ctl.QueryInterface(ISimpleAudioVolume)
            return {
                "process_name": s.Process.name(),
                "volume_percent": round(vol_iface.GetMasterVolume() * 100),
                "muted": bool(vol_iface.GetMute()),
            }
        except Exception as e:
            return {"error": str(e)}

    def set_app_volume(self, app_name: str, level: int, confirm: bool = False) -> Dict:
        """Set a specific app's mixer volume (0-100) by process name.
        Not confirm-gated - a per-app, easily-reversible preference,
        same class as the master volume slider."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            matches = self._find_sessions(app_name)
            if not matches:
                return {"error": f"No running app with an audio session matching '{app_name}'."}
            level = max(0, min(100, level))
            applied = []
            for s in matches:
                vol_iface = s._ctl.QueryInterface(ISimpleAudioVolume)
                vol_iface.SetMasterVolume(level / 100, None)
                applied.append(s.Process.name())
            return {"success": True, "matched_processes": applied, "volume_percent": level}
        except Exception as e:
            return {"error": str(e)}

    def set_app_mute(self, app_name: str, muted: bool, confirm: bool = False) -> Dict:
        """Mute/unmute a specific app in the Volume Mixer by process
        name. Not confirm-gated."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            matches = self._find_sessions(app_name)
            if not matches:
                return {"error": f"No running app with an audio session matching '{app_name}'."}
            applied = []
            for s in matches:
                vol_iface = s._ctl.QueryInterface(ISimpleAudioVolume)
                vol_iface.SetMute(1 if muted else 0, None)
                applied.append(s.Process.name())
            return {"success": True, "matched_processes": applied, "muted": muted}
        except Exception as e:
            return {"error": str(e)}

    # -- Sound scheme ---------------------------------------------------------
    def get_sound_scheme(self) -> Dict:
        """Read the currently active sound scheme name."""
        result = self._run_ps(
            f'(Get-ItemProperty -Path "Registry::{self._SCHEMES_KEY}" -Name ".Current" -ErrorAction SilentlyContinue).".Current"'
        )
        if "error" in result or not result.get("success"):
            return {"error": "Could not read the current sound scheme."}
        return {"sound_scheme": result["stdout"].strip() or ".Default"}

    def list_sound_schemes(self) -> Dict:
        """List available sound scheme names."""
        result = self._run_ps(
            f'Get-ChildItem -Path "Registry::{self._SCHEMES_KEY}" -ErrorAction SilentlyContinue | '
            "Where-Object { $_.PSChildName -notlike '.*' } | ForEach-Object { $_.PSChildName }"
        )
        if "error" in result or not result.get("success"):
            return {"schemes": [], "count": 0}
        schemes = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
        return {"schemes": schemes, "count": len(schemes)}

    def apply_sound_scheme(self, scheme_name: str, confirm: bool = False) -> Dict:
        """Switch the active sound scheme (which .wav plays for system
        events like errors/notifications). Not confirm-gated - purely
        cosmetic, mirrors theme_manager.py's apply_theme precedent."""
        script = (
            f'New-Item -Path "Registry::{self._SCHEMES_KEY}" -Force | Out-Null; '
            f'Set-ItemProperty -Path "Registry::{self._SCHEMES_KEY}" -Name ".Current" -Value "{scheme_name}" -Type String -Force'
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Failed to apply the sound scheme."}
        return {"success": True, "sound_scheme": scheme_name}
