"""
Twitter/X integration
======================
Post tweets and read a user's recent tweets via the X (Twitter) API v2.
Two different auth modes for two different jobs, since X's free tier
splits them:

  - Posting (create/delete a tweet) needs user-context OAuth 1.0a
    (consumer key/secret + access token/secret from a User Auth-enabled
    app at developer.x.com) - this is what actually posts *as you*.
  - Reading (search/user timeline) uses the simpler App-only Bearer
    token, but the free tier's read access is heavily rate-limited
    (a handful of requests per 15 minutes) - expect 429s under normal use.

Setup (.env): TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN,
TWITTER_ACCESS_TOKEN_SECRET (posting), TWITTER_BEARER_TOKEN (reading).

    pip install requests-oauthlib   # OAuth 1.0a request signing for posting
"""

import os
from typing import Dict, Optional

import requests

try:
    from requests_oauthlib import OAuth1

    HAS_OAUTH1 = True
except ImportError:
    HAS_OAUTH1 = False

API_URL = "https://api.twitter.com/2"


class TwitterPoster:
    """Post/delete tweets (OAuth 1.0a user context) and read a user's
    recent tweets (App-only Bearer token)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_token_secret: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("TWITTER_API_KEY")
        self.api_secret = api_secret or os.getenv("TWITTER_API_SECRET")
        self.access_token = access_token or os.getenv("TWITTER_ACCESS_TOKEN")
        self.access_token_secret = access_token_secret or os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")

    def is_configured(self) -> bool:
        """Posting readiness - the OAuth 1.0a user-context credentials."""
        return HAS_OAUTH1 and bool(self.api_key and self.api_secret and self.access_token and self.access_token_secret)

    def is_read_configured(self) -> bool:
        return bool(self.bearer_token)

    def _auth(self):
        return OAuth1(self.api_key, self.api_secret, self.access_token, self.access_token_secret)

    # -- posting (OAuth 1.0a user context) ---------------------------------
    def post_tweet(self, text: str, reply_to_tweet_id: Optional[str] = None) -> Dict:
        if not HAS_OAUTH1:
            return {"success": False, "error": "requests-oauthlib not installed - run: pip install requests-oauthlib"}
        if not self.is_configured():
            return {
                "success": False,
                "error": "Twitter posting credentials not set - need TWITTER_API_KEY, "
                "TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET",
            }
        try:
            payload: Dict = {"text": text}
            if reply_to_tweet_id:
                payload["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
            resp = requests.post(f"{API_URL}/tweets", auth=self._auth(), json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            return {"success": True, "tweet_id": data.get("id"), "text": data.get("text")}
        except requests.HTTPError as e:
            return {"success": False, "error": f"{e} - {e.response.text[:300] if e.response is not None else ''}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_tweet(self, tweet_id: str) -> Dict:
        if not self.is_configured():
            return {"success": False, "error": "Twitter posting credentials not set."}
        try:
            resp = requests.delete(f"{API_URL}/tweets/{tweet_id}", auth=self._auth(), timeout=15)
            resp.raise_for_status()
            deleted = resp.json().get("data", {}).get("deleted", False)
            return {"success": True, "tweet_id": tweet_id, "deleted": deleted}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # -- reading (App-only Bearer token) -------------------------------------
    def _bearer_headers(self) -> Dict:
        return {"Authorization": f"Bearer {self.bearer_token}"}

    def get_user_id(self, username: str) -> Dict:
        if not self.is_read_configured():
            return {"success": False, "error": "TWITTER_BEARER_TOKEN not set."}
        try:
            resp = requests.get(f"{API_URL}/users/by/username/{username}", headers=self._bearer_headers(), timeout=15)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            if not data:
                return {"success": False, "error": f"No such user: @{username}"}
            return {"success": True, "id": data["id"], "name": data.get("name"), "username": data.get("username")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_user_tweets(self, username: str, max_results: int = 10) -> Dict:
        """Recent tweets from `username`'s timeline (max_results: 5-100)."""
        user = self.get_user_id(username)
        if not user.get("success"):
            return user
        try:
            resp = requests.get(
                f"{API_URL}/users/{user['id']}/tweets",
                headers=self._bearer_headers(),
                params={"max_results": max(5, min(max_results, 100)), "tweet.fields": "created_at,public_metrics"},
                timeout=15,
            )
            resp.raise_for_status()
            tweets = [
                {
                    "id": t["id"],
                    "text": t["text"],
                    "created_at": t.get("created_at"),
                    "likes": t.get("public_metrics", {}).get("like_count"),
                    "retweets": t.get("public_metrics", {}).get("retweet_count"),
                }
                for t in resp.json().get("data", [])
            ]
            return {"success": True, "username": username, "count": len(tweets), "tweets": tweets}
        except Exception as e:
            return {"success": False, "error": str(e)}
