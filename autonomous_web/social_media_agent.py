"""
social_media_agent.py
======================
Lets ULTRON post/schedule content the user has written to their own
social accounts.

Design choice, explained: this talks to platforms' OFFICIAL APIs with
a token the user generates and supplies themselves - the same
approach tools like Buffer or Hootsuite use. It does not drive a
headless browser to click through a social site's normal UI. That
distinction matters: officially-sanctioned API access with a
user-issued token is the account owner using their own account, while
browser automation that mimics human clicks (especially paired with
captcha-bypassing, which this project also doesn't build) is the
pattern platforms' bot-detection exists to catch, and using it to
manage accounts violates most platforms' terms of service regardless
of whether the account is your own.

If a platform you want doesn't have this content, that's a signal to
skip automating it, not to switch to the UI-clicking approach.
Currently wired: X/Twitter (v2 API) and a generic webhook poster you
can point at anything with an HTTP API (Discord, Slack, a personal
blog's publish endpoint, etc).

Dependencies: pip install requests
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests

logger = logging.getLogger("ultron.social_media_agent")


@dataclass
class PostResult:
    success: bool
    platform: str
    post_id: Optional[str] = None
    error: Optional[str] = None


class SocialMediaAgent:
    def __init__(self):
        self._tokens = {}  # platform -> credentials dict, set via configure()

    def configure(self, platform: str, **credentials):
        """e.g. configure('twitter', bearer_token='...')"""
        self._tokens[platform] = credentials
        logger.info("Configured credentials for platform: %s", platform)

    # ------------------------------------------------------------- X/Twitter
    def post_to_twitter(self, text: str) -> PostResult:
        creds = self._tokens.get("twitter")
        if not creds or "bearer_token" not in creds:
            return PostResult(False, "twitter", error="Not configured - call configure('twitter', bearer_token=...)")

        try:
            resp = requests.post(
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {creds['bearer_token']}", "Content-Type": "application/json"},
                json={"text": text},
                timeout=10,
            )
            if resp.status_code in (200, 201):
                post_id = resp.json().get("data", {}).get("id")
                logger.info("Posted to Twitter/X: %s", post_id)
                return PostResult(True, "twitter", post_id=post_id)
            return PostResult(False, "twitter", error=f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            return PostResult(False, "twitter", error=str(e))

    # ------------------------------------------------------ generic webhook
    def post_to_webhook(self, platform_name: str, webhook_url: str, payload: dict) -> PostResult:
        """Generic path for anything with an HTTP publish endpoint - Discord
        webhooks, Slack incoming webhooks, a personal CMS, etc."""
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            if resp.ok:
                return PostResult(True, platform_name)
            return PostResult(False, platform_name, error=f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            return PostResult(False, platform_name, error=str(e))

    # --------------------------------------------------------------- queue
    def post(self, platform: str, text: str, **kwargs) -> PostResult:
        """Dispatch by platform name."""
        if platform == "twitter":
            return self.post_to_twitter(text)
        if platform == "webhook":
            return self.post_to_webhook(
                kwargs.get("platform_name", "webhook"), kwargs["webhook_url"], kwargs.get("payload", {"content": text})
            )
        return PostResult(False, platform, error=f"Unsupported platform: {platform}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = SocialMediaAgent()
    # agent.configure("twitter", bearer_token="YOUR_TOKEN")
    # print(agent.post("twitter", "Hello from ULTRON"))
    print("Configure credentials with agent.configure(...) before posting.")
