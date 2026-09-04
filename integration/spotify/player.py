"""
Spotify integration
====================
Playback control and search via the Spotify Web API, authenticated with
the Authorization Code flow (needs a logged-in user + an active Spotify
device - phone, desktop app, or web player - since the Web API only
*controls* playback, it doesn't stream audio itself).

Setup (.env):
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET - from developer.spotify.com/dashboard
    SPOTIFY_REDIRECT_URI - defaults to http://127.0.0.1:8888/callback
      (must be added to the app's Redirect URIs in the dashboard)
First call opens a browser for login consent; refresh token is cached at
storage/cache/spotify_token.json.
"""

import json
import os
import webbrowser
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlencode

import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing playlist-read-private"


class SpotifyClient:
    """Wrapper around the Spotify Web API for search + playback control."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
        self.token_path = Path(token_path or BASE_DIR / "storage" / "cache" / "spotify_token.json")

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # -- auth -----------------------------------------------------------
    def get_auth_url(self) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def authorize_interactive(self) -> Dict:
        """Opens the consent page; the user must paste back the redirected
        URL (containing ?code=...) since we don't run a local callback server."""
        if not self.is_configured():
            return {"success": False, "error": "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env"}
        url = self.get_auth_url()
        webbrowser.open(url)
        return {
            "success": True,
            "auth_url": url,
            "next_step": "Call exchange_code(code) with the ?code= value from the redirected URL",
        }

    def exchange_code(self, code: str) -> Dict:
        try:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                auth=(self.client_id, self.client_secret),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(json.dumps(data))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_access_token(self) -> str:
        if not self.token_path.exists():
            raise RuntimeError("Not authorized yet - call authorize_interactive() then exchange_code().")
        data = json.loads(self.token_path.read_text())
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": data["refresh_token"],
            },
            auth=(self.client_id, self.client_secret),
            timeout=15,
        )
        resp.raise_for_status()
        new_data = resp.json()
        data.update(new_data)
        self.token_path.write_text(json.dumps(data))
        return data["access_token"]

    def _headers(self) -> Dict:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    # -- search -----------------------------------------------------------
    def search_track(self, query: str, limit: int = 5) -> Dict:
        try:
            resp = requests.get(
                f"{API_URL}/search",
                headers=self._headers(),
                params={"q": query, "type": "track", "limit": limit},
                timeout=15,
            )
            resp.raise_for_status()
            tracks = [
                {
                    "name": t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "uri": t["uri"],
                    "album": t["album"]["name"],
                }
                for t in resp.json()["tracks"]["items"]
            ]
            return {"success": True, "count": len(tracks), "tracks": tracks}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- playback control ------------------------------------------------
    def play(self, track_uri: Optional[str] = None, device_id: Optional[str] = None) -> Dict:
        try:
            params = {"device_id": device_id} if device_id else {}
            body = {"uris": [track_uri]} if track_uri else {}
            resp = requests.put(
                f"{API_URL}/me/player/play", headers=self._headers(), params=params, json=body, timeout=15
            )
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def pause(self) -> Dict:
        try:
            resp = requests.put(f"{API_URL}/me/player/pause", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def next_track(self) -> Dict:
        try:
            resp = requests.post(f"{API_URL}/me/player/next", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def previous_track(self) -> Dict:
        try:
            resp = requests.post(f"{API_URL}/me/player/previous", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_volume(self, percent: int) -> Dict:
        try:
            resp = requests.put(
                f"{API_URL}/me/player/volume",
                headers=self._headers(),
                params={"volume_percent": max(0, min(100, percent))},
                timeout=15,
            )
            resp.raise_for_status()
            return {"success": True, "volume": percent}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def current_playback(self) -> Dict:
        try:
            resp = requests.get(f"{API_URL}/me/player", headers=self._headers(), timeout=15)
            if resp.status_code == 204:
                return {"success": True, "playing": False}
            resp.raise_for_status()
            data = resp.json()
            item = data.get("item") or {}
            return {
                "success": True,
                "playing": data.get("is_playing", False),
                "track": item.get("name"),
                "artist": ", ".join(a["name"] for a in item.get("artists", [])),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_playlists(self, limit: int = 20) -> Dict:
        try:
            resp = requests.get(f"{API_URL}/me/playlists", headers=self._headers(), params={"limit": limit}, timeout=15)
            resp.raise_for_status()
            playlists = [
                {"name": p["name"], "id": p["id"], "tracks": p["tracks"]["total"]} for p in resp.json()["items"]
            ]
            return {"success": True, "count": len(playlists), "playlists": playlists}
        except Exception as e:
            return {"success": False, "error": str(e)}
