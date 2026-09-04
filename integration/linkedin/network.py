"""
LinkedIn integration
======================
Read the authenticated user's profile and post text updates via the
LinkedIn API, authenticated with the standard OAuth 2.0 Authorization
Code flow (same shape as integration/spotify/player.py's: open a
consent page, paste back the redirected ?code=, cache the resulting
token). Two LinkedIn "products" are needed on the app at
linkedin.com/developers, both free to request:

  - "Sign In with LinkedIn using OpenID Connect" - profile info (name,
    email) via /v2/userinfo, scope: openid profile email
  - "Share on LinkedIn" - posting via /rest/posts, scope: w_member_social

Setup (.env):
    LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET - from the app's Auth tab
    LINKEDIN_REDIRECT_URI - defaults to http://localhost:8000/callback
      (must exactly match a Redirect URL configured on the app)
Refresh token is cached at storage/cache/linkedin_token.json.
"""

import json
import os
import webbrowser
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlencode

import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API_URL = "https://api.linkedin.com/v2"
REST_URL = "https://api.linkedin.com/rest"
SCOPES = "openid profile email w_member_social"
LINKEDIN_API_VERSION = "202405"  # /rest/* endpoints require a pinned monthly version


class LinkedInNetwork:
    """Wrapper around the LinkedIn API for profile lookup + posting."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        self.client_id = client_id or os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("LINKEDIN_CLIENT_SECRET")
        self.redirect_uri = redirect_uri or os.getenv("LINKEDIN_REDIRECT_URI", "http://localhost:8000/callback")
        self.token_path = Path(token_path or BASE_DIR / "storage" / "cache" / "linkedin_token.json")
        self._member_urn: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # -- auth -----------------------------------------------------------
    def get_auth_url(self) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPES,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def authorize_interactive(self) -> Dict:
        """Opens the consent page; paste back the ?code= from the
        redirected URL into exchange_code()."""
        if not self.is_configured():
            return {"success": False, "error": "Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env"}
        url = self.get_auth_url()
        webbrowser.open(url)
        return {"success": True, "auth_url": url, "next_step": "Call exchange_code(code) with the ?code= value"}

    def exchange_code(self, code: str) -> Dict:
        try:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            # LinkedIn access tokens are long-lived (~60 days) and this
            # flow doesn't issue a refresh token by default - once this
            # expires, authorize_interactive() again.
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(json.dumps(data))
            return {"success": True, "expires_in": data.get("expires_in")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_access_token(self) -> str:
        if not self.token_path.exists():
            raise RuntimeError("Not authorized yet - call authorize_interactive() then exchange_code().")
        data = json.loads(self.token_path.read_text())
        if "access_token" not in data:
            raise RuntimeError("Cached LinkedIn token is missing access_token - re-authorize.")
        return data["access_token"]

    def _headers(self, rest: bool = False) -> Dict:
        headers = {"Authorization": f"Bearer {self._get_access_token()}"}
        if rest:
            headers["LinkedIn-Version"] = LINKEDIN_API_VERSION
            headers["X-Restli-Protocol-Version"] = "2.0.0"
        return headers

    # -- profile ------------------------------------------------------------
    def get_profile(self) -> Dict:
        try:
            resp = requests.get(f"{API_URL}/userinfo", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self._member_urn = f"urn:li:person:{data['sub']}"
            return {"success": True, "name": data.get("name"), "email": data.get("email"), "urn": self._member_urn}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_member_urn(self) -> str:
        if not self._member_urn:
            profile = self.get_profile()
            if not profile.get("success"):
                raise RuntimeError(profile.get("error", "Could not resolve member URN"))
        return self._member_urn

    # -- posting --------------------------------------------------------------
    def post_update(self, text: str, visibility: str = "PUBLIC") -> Dict:
        """Post a plain-text update to the authenticated user's feed.
        visibility: 'PUBLIC' or 'CONNECTIONS'."""
        try:
            author = self._get_member_urn()
            payload = {
                "author": author,
                "commentary": text,
                "visibility": visibility,
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            }
            resp = requests.post(f"{REST_URL}/posts", headers=self._headers(rest=True), json=payload, timeout=15)
            resp.raise_for_status()
            post_id = resp.headers.get("x-restli-id") or resp.headers.get("x-linkedin-id")
            return {"success": True, "post_id": post_id}
        except requests.HTTPError as e:
            return {"success": False, "error": f"{e} - {e.response.text[:300] if e.response is not None else ''}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
