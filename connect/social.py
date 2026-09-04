"""
Social (CONNECT)
===================
Deliberately scoped narrower than its name might suggest, the same
way people_search.py (Phase 18.5) is: this module posts a message to
whatever pre-configured webhook URLs the caller has set up, one HTTP
POST per platform. It does not, and will not, grow into:

  - native OAuth posting to Twitter/X, Instagram, Facebook, or
    LinkedIn's own APIs
  - managing access tokens, refresh flows, or per-platform auth of
    any kind
  - reading a feed, timeline, or engagement metrics back

That's a scoping decision, not an oversight: those platforms require
a registered developer app, user OAuth consent, and often manual
review before posting is even possible - infrastructure this project
doesn't have and that a single generic module can't respectably fake.
A webhook (Slack/Discord incoming webhooks, a Zapier/IFTTT relay that
fans out to Twitter or Instagram on the caller's behalf, etc.) sidesteps
all of that by pushing the actual platform auth to a service built for
it, which is the same "working integration over from-scratch
implementation" preference PHASE_18_5_SEARCH_ENGINE's own docstring
names.

Each target is one environment variable named SOCIAL_WEBHOOK_<NAME>
(e.g. SOCIAL_WEBHOOK_DISCORD, SOCIAL_WEBHOOK_SLACK) holding that
webhook's URL - never hardcoded here. post() discovers configured
targets by scanning os.environ for that prefix, so adding a new
platform is just setting one more env var, no code change. Same
empty/failure-safe contract as the rest of this project: a target
whose POST fails is reported in `failed`, never raised.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

WEBHOOK_ENV_PREFIX = "SOCIAL_WEBHOOK_"
DEFAULT_TIMEOUT_SECONDS = 8


class SocialConnect:
    """Webhook fan-out poster. Use get_social()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(self._configured_targets())

    def post(self, text: str, platforms: Optional[List[str]] = None) -> Dict:
        """Posts `text` to every configured SOCIAL_WEBHOOK_* target,
        or only the ones named in `platforms` (case-insensitive,
        matching the part of the env var after the prefix - e.g.
        ["discord"] for SOCIAL_WEBHOOK_DISCORD). Returns
        {"success": bool, "posted_to": List[str], "failed": List[str],
        "error": Optional[str]}. `success` is True if at least one
        target succeeded; individual failures still land in `failed`
        rather than aborting the rest."""
        if not _REQUESTS_AVAILABLE:
            return {"success": False, "posted_to": [], "failed": [], "error": "requests not available"}
        if not text:
            return {"success": False, "posted_to": [], "failed": [], "error": "no text given"}

        targets = self._configured_targets()
        if platforms:
            wanted = {p.lower() for p in platforms}
            targets = {name: url for name, url in targets.items() if name.lower() in wanted}
        if not targets:
            return {"success": False, "posted_to": [], "failed": [], "error": "no configured targets"}

        posted_to: List[str] = []
        failed: List[str] = []
        for name, url in targets.items():
            try:
                response = requests.post(url, json={"text": text}, timeout=DEFAULT_TIMEOUT_SECONDS)
                response.raise_for_status()
                posted_to.append(name)
            except Exception:
                failed.append(name)

        return {"success": bool(posted_to), "posted_to": posted_to, "failed": failed, "error": None}

    @staticmethod
    def _configured_targets() -> Dict[str, str]:
        return {
            key[len(WEBHOOK_ENV_PREFIX) :].lower(): value
            for key, value in os.environ.items()
            if key.startswith(WEBHOOK_ENV_PREFIX) and value
        }


_social: Optional[SocialConnect] = None


def get_social() -> SocialConnect:
    global _social
    if _social is None:
        _social = SocialConnect()
    return _social
