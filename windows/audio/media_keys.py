"""Media keys
===========
System-wide media key simulation (play/pause/next/prev/volume) for whatever app is playing audio.
"""

import ctypes
from typing import Dict


class MediaKeys:
    """Simulate system-wide media keys (works with Spotify, VLC, browser tabs, etc)."""

    def _media_key(self, vk_code: int) -> Dict:
        try:
            KEYEVENTF_EXTENDEDKEY = 0x1
            KEYEVENTF_KEYUP = 0x2
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def media_play_pause(self) -> Dict:
        """Play/pause whatever media is active system-wide."""
        return self._media_key(0xB3)

    def media_next(self) -> Dict:
        """Skip to next track system-wide."""
        return self._media_key(0xB0)

    def media_previous(self) -> Dict:
        """Go to previous track system-wide."""
        return self._media_key(0xB1)

    def media_volume_up(self) -> Dict:
        """System volume up (media key)."""
        return self._media_key(0xAF)

    def media_volume_down(self) -> Dict:
        """System volume down (media key)."""
        return self._media_key(0xAE)

    def media_mute(self) -> Dict:
        """Toggle system mute (media key)."""
        return self._media_key(0xAD)
