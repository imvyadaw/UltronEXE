"""
Fact Check
==========
Wraps Google's Fact Check Tools API - a purpose-built claim-search
index of what fact-checking organizations have actually published,
not this project inventing its own true/false judgment. That
distinction matters: check_claim() returns what publishers have rated
a similar claim, with attribution, and returns an empty list rather
than a verdict when nothing matches - the same "flag, don't conclude"
posture EYES/threat_sense.py already takes for hazards, applied here
to claims instead of camera frames.

Reuses google_search.py's API key env var (GOOGLE_SEARCH_API_KEY) -
the Fact Check Tools API is enabled per-project on the same Google
Cloud API key, not a separate credential, so a second env var would
just be one more thing to keep in sync for no benefit.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

API_KEY_ENV = "GOOGLE_SEARCH_API_KEY"
ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_PAGE_SIZE = 5


class FactCheck:
    """Published fact-check lookups via Google Fact Check Tools API. Use get_fact_check()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(API_KEY_ENV))

    def check_claim(self, query: str, num: int = DEFAULT_PAGE_SIZE) -> List[Dict]:
        """Returns up to `num` matching published fact-checks as
        {"claim_text": str, "claimant": str, "rating": str,
        "publisher": str, "url": str}. Empty list means "no fact-check
        publisher has covered a matching claim" just as much as it
        means "backend unavailable" - callers needing to tell those
        apart should call is_available() first."""
        if not self.is_available() or not query:
            return []
        try:
            response = requests.get(
                ENDPOINT,
                params={"key": os.environ[API_KEY_ENV], "query": query, "pageSize": max(1, num)},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            claims = data.get("claims", [])
            results = []
            for c in claims:
                reviews = c.get("claimReview", [])
                review = reviews[0] if reviews else {}
                results.append(
                    {
                        "claim_text": c.get("text", ""),
                        "claimant": c.get("claimant", ""),
                        "rating": review.get("textualRating", ""),
                        "publisher": (review.get("publisher") or {}).get("name", ""),
                        "url": review.get("url", ""),
                    }
                )
            return results
        except Exception:
            return []


_fact_check: Optional[FactCheck] = None


def get_fact_check() -> FactCheck:
    global _fact_check
    if _fact_check is None:
        _fact_check = FactCheck()
    return _fact_check
