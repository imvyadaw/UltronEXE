"""
News Search
===========
A separate backend from google_search.py's - NewsAPI.org rather than
Custom Search - because news wants fields Custom Search doesn't give
cleanly (a real publish timestamp, a distinct source name), the same
reason COMMAND/reports.py builds its own digest instead of reusing
history.py's generic timeline shape. Requires a NewsAPI key in
NEWS_API_KEY; same empty-list-on-any-failure contract as the rest of
this phase.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

API_KEY_ENV = "NEWS_API_KEY"
ENDPOINT = "https://newsapi.org/v2/everything"
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_PAGE_SIZE = 5
MAX_PAGE_SIZE = 20


class NewsSearch:
    """News search via NewsAPI.org. Use get_news_search()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(API_KEY_ENV))

    def search(self, query: str, num: int = DEFAULT_PAGE_SIZE, language: str = "en") -> List[Dict]:
        """Returns up to `num` articles, most-recent first, as
        {"title": str, "source": str, "url": str, "published_at": str,
        "snippet": str}. Empty list on no backend, no query, or any
        request failure."""
        if not self.is_available() or not query:
            return []
        try:
            response = requests.get(
                ENDPOINT,
                params={
                    "apiKey": os.environ[API_KEY_ENV],
                    "q": query,
                    "language": language,
                    "sortBy": "publishedAt",
                    "pageSize": max(1, min(num, MAX_PAGE_SIZE)),
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            articles = data.get("articles", [])
            return [
                {
                    "title": a.get("title", ""),
                    "source": (a.get("source") or {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published_at": a.get("publishedAt", ""),
                    "snippet": a.get("description") or "",
                }
                for a in articles
            ]
        except Exception:
            return []


_news_search: Optional[NewsSearch] = None


def get_news_search() -> NewsSearch:
    global _news_search
    if _news_search is None:
        _news_search = NewsSearch()
    return _news_search
