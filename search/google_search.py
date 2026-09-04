"""
Google Search
=============
The base web-search backend for this phase - image_search.py,
price_search.py, and people_search.py all build on the same Google
Custom Search JSON API call this module makes, the same way
threat_sense.py's stranger check builds on face_scanner.py instead of
duplicating detection logic. Requires a Custom Search Engine (any CSE
configured to search the whole web, or a scoped one) plus an API key,
both read from environment variables - no key is hardcoded here, and
none should ever be committed alongside this file.

Same contract as every other optional-dependency module in this
project: no `requests` package, no API key, no network reachable, or a
non-2xx/error response from Google all collapse to the same empty
result rather than an exception. This module does not cache, retry,
or rate-limit beyond what a single request naturally does - a caller
making many calls in a loop is responsible for its own pacing against
the API's quota.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

API_KEY_ENV = "GOOGLE_SEARCH_API_KEY"
CSE_ID_ENV = "GOOGLE_SEARCH_CSE_ID"
ENDPOINT = "https://www.googleapis.com/customsearch/v1"
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_NUM_RESULTS = 5
MAX_NUM_RESULTS = 10  # the API's own per-request ceiling


class GoogleSearch:
    """Web search via Google Custom Search JSON API. Use get_google_search()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(API_KEY_ENV)) and bool(os.environ.get(CSE_ID_ENV))

    def search(self, query: str, num: int = DEFAULT_NUM_RESULTS, site: Optional[str] = None) -> List[Dict]:
        """Returns up to `num` results as
        {"title": str, "url": str, "snippet": str}. `site`, if given,
        is folded into the query as a `site:` restriction rather than
        a second API param, since Custom Search doesn't expose
        site-restriction as its own field. Empty list on no backend,
        no query, or any request failure."""
        if not self.is_available() or not query:
            return []
        full_query = f"site:{site} {query}" if site else query
        try:
            response = requests.get(
                ENDPOINT,
                params={
                    "key": os.environ[API_KEY_ENV],
                    "cx": os.environ[CSE_ID_ENV],
                    "q": full_query,
                    "num": max(1, min(num, MAX_NUM_RESULTS)),
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            return [
                {"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", "")} for i in items
            ]
        except Exception:
            return []


_google_search: Optional[GoogleSearch] = None


def get_google_search() -> GoogleSearch:
    global _google_search
    if _google_search is None:
        _google_search = GoogleSearch()
    return _google_search
