"""Media Control
================
OS-wide "whatever is currently playing" media control - distinct from
apps/media/*.py (spotify.py, vlc.py, itunes.py, windows_media.py,
youtube_music.py), which each drive one *named* app through its own
API/window (Spotify's local HTTP client, VLC's HTTP interface, ...).
This module instead sends the same virtual media keys the hardware
keys on a keyboard send (VK_MEDIA_PLAY_PAUSE etc, via
user32.keybd_event), which whichever app currently holds the System
Media Transport Controls (SMTC) session receives - no per-app
integration needed, and it works for apps with no local API at all
(browser tabs playing YouTube, UWP media apps, ...).

Reading *what's* currently playing (title/artist/app) requires the
WinRT GlobalSystemMediaTransportControlsSessionManager API, which is
only available if the optional `winsdk` (or `winrt`) package is
installed - get_now_playing_info() degrades gracefully to an
{"error": ...} explaining that, rather than raising, when it isn't.
"""

import ctypes
from typing import Dict

# Virtual key codes for the extended media keys (winuser.h).
_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_MEDIA_STOP = 0xB2
_VK_MEDIA_NEXT_TRACK = 0xB0
_VK_MEDIA_PREV_TRACK = 0xB1
_VK_VOLUME_MUTE = 0xAD
_VK_VOLUME_UP = 0xAF
_VK_VOLUME_DOWN = 0xAE

_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002


class MediaControl:
    """OS-wide media-key control of whichever app owns the current
    media session, plus best-effort now-playing info."""

    def _send_key(self, vk_code: int) -> Dict:
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk_code, 0, _KEYEVENTF_EXTENDEDKEY, 0)
            user32.keybd_event(vk_code, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, 0)
            return {"success": True}
        except AttributeError:
            return {"error": "ctypes.windll not available - this is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def play_pause(self) -> Dict:
        """Toggle play/pause on whichever app owns the current media
        session. No admin needed, no confirmation needed - identical
        effect to pressing the hardware media key."""
        return self._send_key(_VK_MEDIA_PLAY_PAUSE)

    def stop(self) -> Dict:
        """Send the media-stop key."""
        return self._send_key(_VK_MEDIA_STOP)

    def next_track(self) -> Dict:
        """Send the next-track key."""
        return self._send_key(_VK_MEDIA_NEXT_TRACK)

    def previous_track(self) -> Dict:
        """Send the previous-track key."""
        return self._send_key(_VK_MEDIA_PREV_TRACK)

    def set_mute(self, muted: bool) -> Dict:
        """Toggle system volume mute. Windows exposes this as a single
        toggle key rather than separate mute/unmute, so this sends the
        mute key regardless of the requested state - callers should
        check the result or query current mute state via
        windows/audio/volume.py first if exact state matters."""
        return self._send_key(_VK_VOLUME_MUTE)

    def volume_up(self, steps: int = 1) -> Dict:
        """Send the volume-up key `steps` times (each step is one
        Windows volume increment, ~2%)."""
        for _ in range(max(1, steps)):
            result = self._send_key(_VK_VOLUME_UP)
            if "error" in result:
                return result
        return {"success": True, "steps": steps}

    def volume_down(self, steps: int = 1) -> Dict:
        """Send the volume-down key `steps` times."""
        for _ in range(max(1, steps)):
            result = self._send_key(_VK_VOLUME_DOWN)
            if "error" in result:
                return result
        return {"success": True, "steps": steps}

    def get_now_playing_info(self) -> Dict:
        """Best-effort read of the current SMTC session's title/artist/
        app via the WinRT GlobalSystemMediaTransportControlsSessionManager
        API. Requires the optional `winsdk` package; returns a clear
        {"error": ...} (not a raise) if it isn't installed, matching
        this codebase's graceful-degradation convention (see
        ai/embeddings.py)."""
        try:
            import asyncio
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as SessionManager,
            )
        except ImportError:
            return {
                "error": "Optional dependency 'winsdk' not installed - now-playing info unavailable. Install with: pip install winsdk"
            }

        async def _read():
            manager = await SessionManager.request_async()
            session = manager.get_current_session()
            if session is None:
                return {"playing": False}
            info = await session.try_get_media_properties_async()
            playback_info = session.get_playback_info()
            return {
                "playing": True,
                "title": info.title,
                "artist": info.artist,
                "album_title": info.album_title,
                "app_id": session.source_app_user_model_id,
                "playback_status": str(playback_info.playback_status) if playback_info else None,
            }

        try:
            return asyncio.run(_read())
        except Exception as e:
            return {"error": str(e)}
