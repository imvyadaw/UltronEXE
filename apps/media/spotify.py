"""
Spotify automation
=====================
Prefers the real Spotify Web API (integration/spotify/spotify_client.py -
SpotifyClient) when SPOTIFY_CLIENT_ID/SECRET are configured, since that
gives real search/queue/playlist control. Falls back to system media-key
playback control (works against whichever media app - including
Spotify - currently owns the OS media session) when it isn't.
"""

from typing import Dict

from apps.base_app import BaseApp

try:
    import pyautogui

    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class SpotifyApp(BaseApp):
    """Search/play via the Spotify Web API, or fall back to media keys."""

    APP_NAME = "spotify"
    PROCESS_NAMES = ["spotify.exe", "spotify"]
    EXE_HINTS = ["spotify", "spotify.exe"]

    def __init__(self):
        super().__init__()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from integration.spotify.player import SpotifyClient

            self._client = SpotifyClient()
        return self._client

    def search_and_play(self, query: str) -> Dict:
        client = self._get_client()
        if client.is_configured():
            results = client.search_track(query, limit=1)
            tracks = results.get("tracks") or []
            if results.get("success") and tracks:
                uri = tracks[0].get("uri")
                return client.play(track_uri=uri) if uri else results
            return results
        opened = self.open()
        return {
            **opened,
            "note": "Spotify Web API not configured (SPOTIFY_CLIENT_ID/SECRET) - opened the app instead; use search bar manually",
        }

    def play_pause(self) -> Dict:
        client = self._get_client()
        if client.is_configured():
            playback = client.current_playback()
            if playback.get("success") and playback.get("is_playing"):
                return client.pause()
            return client.play()
        return self._media_key("playpause")

    def next_track(self) -> Dict:
        client = self._get_client()
        if client.is_configured():
            return client.next_track()
        return self._media_key("nexttrack")

    def previous_track(self) -> Dict:
        client = self._get_client()
        if client.is_configured():
            return client.previous_track()
        return self._media_key("prevtrack")

    def _media_key(self, key: str) -> Dict:
        if not HAS_PYAUTOGUI:
            return {"error": "pyautogui not installed - run: pip install pyautogui"}
        try:
            pyautogui.press(key)
            return {"success": True, "key": key, "note": "sent as a system media key"}
        except Exception as e:
            return {"error": str(e)}
