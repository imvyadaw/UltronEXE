"""Volume control
===============
System volume get/set/mute via pycaw.
"""

from typing import Dict

try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False


class VolumeControl:
    """Get/set/mute the system volume via pycaw."""

    def _get_volume_interface(self):
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    def set_volume(self, level: int) -> Dict:
        """Set system volume (0-100)."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            level = max(0, min(100, level))
            self._get_volume_interface().SetMasterVolumeLevelScalar(level / 100, None)
            return {"success": True, "volume": level}
        except Exception as e:
            return {"error": str(e)}

    def get_volume(self) -> Dict:
        """Get current system volume."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            level = round(self._get_volume_interface().GetMasterVolumeLevelScalar() * 100)
            return {"volume": level}
        except Exception as e:
            return {"error": str(e)}

    def mute(self) -> Dict:
        """Mute system audio."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            self._get_volume_interface().SetMute(1, None)
            return {"success": True, "muted": True}
        except Exception as e:
            return {"error": str(e)}

    def unmute(self) -> Dict:
        """Unmute system audio."""
        if not HAS_PYCAW:
            return {"error": "pycaw not installed - run: pip install pycaw comtypes"}
        try:
            self._get_volume_interface().SetMute(0, None)
            return {"success": True, "muted": False}
        except Exception as e:
            return {"error": str(e)}
