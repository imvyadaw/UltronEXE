"""
Spotify (CONNECT)
===================
Controls playback and searches tracks via the Spotify Web API over
`requests` - a real HTTP call to Spotify's servers, no Spotify desktop
app required to be installed or running (beyond having an active
device Spotify already knows about, which the Web API itself
requires). This is a different backend from apps/media/spotify.py
(Phase 6), which drives the installed desktop app directly; prefer
that one when the desktop app is the target, this one when acting on
whatever device is currently active in the user's Spotify account
(including a phone, a speaker, or no local app at all).

Takes a pre-obtained OAuth access token via SPOTIFY_ACCESS_TOKEN, same
"caller keeps it valid" contract as CONNECT/calendar.py - no OAuth
flow is performed here. Same empty/failure-safe contract as the rest
of this project.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

ACCESS_TOKEN_ENV = "SPOTIFY_ACCESS_TOKEN"
API_BASE = "https://api.spotify.com/v1"
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_NUM_RESULTS = 5


class SpotifyConnect:
    """Spotify Web API search/playback. Use get_spotify()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(ACCESS_TOKEN_ENV))

    def search_track(self, query: str, num: int = DEFAULT_NUM_RESULTS) -> List[Dict]:
        """Returns up to `num` matching tracks as
        {"name": str, "artist": str, "uri": str}. Empty list on no
        backend, no query, or any request failure."""
        if not self.is_available() or not query:
            return []
        try:
            response = requests.get(
                f"{API_BASE}/search",
                headers={"Authorization": f"Bearer {os.environ[ACCESS_TOKEN_ENV]}"},
                params={"q": query, "type": "track", "limit": max(1, min(num, 50))},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = (response.json().get("tracks") or {}).get("items", [])
            return [
                {
                    "name": t.get("name", ""),
                    "artist": ", ".join(a.get("name", "") for a in t.get("artists", [])),
                    "uri": t.get("uri", ""),
                }
                for t in items
            ]
        except Exception:
            return []

    def play(self, track_uri: Optional[str] = None, device_id: Optional[str] = None) -> Dict:
        """Starts playback on the account's active device (or
        `device_id` if given). If `track_uri` is given, plays that
        track; otherwise resumes whatever was last playing. Returns
        {"success": bool, "error": Optional[str]}. Requires an
        active/available device on the account already - the Web API
        itself returns an error if there isn't one, which this method
        passes through rather than working around."""
        if not self.is_available():
            return {"success": False, "error": "backend unavailable"}
        try:
            params = {"device_id": device_id} if device_id else {}
            body = {"uris": [track_uri]} if track_uri else {}
            response = requests.put(
                f"{API_BASE}/me/player/play",
                headers={"Authorization": f"Bearer {os.environ[ACCESS_TOKEN_ENV]}"},
                params=params,
                json=body,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def pause(self) -> Dict:
        """Pauses playback on the account's active device. Returns
        {"success": bool, "error": Optional[str]}."""
        if not self.is_available():
            return {"success": False, "error": "backend unavailable"}
        try:
            response = requests.put(
                f"{API_BASE}/me/player/pause",
                headers={"Authorization": f"Bearer {os.environ[ACCESS_TOKEN_ENV]}"},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return {"success": True, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


_spotify: Optional[SpotifyConnect] = None


def get_spotify() -> SpotifyConnect:
    global _spotify
    if _spotify is None:
        _spotify = SpotifyConnect()
    return _spotify
