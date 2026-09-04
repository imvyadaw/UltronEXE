"""
YouTube (CONNECT)
====================
Searches and fetches video metadata via the official YouTube Data API
v3 - a real API call returning structured JSON, not the
scraping-the-search-results-HTML approach `youtube_play()` in
browser/chrome/chrome.py (Phase 16) uses. That scraper stays useful
because it needs no API key and drives an actual visible browser tab;
this module trades that independence for real metadata (view counts,
durations, channel names) a scrape doesn't cleanly give, the same
reason SEARCH/news_search.py chose NewsAPI over google_search.py for
news specifically.

Requires a YOUTUBE_API_KEY environment variable - kept separate from
GOOGLE_SEARCH_API_KEY (unlike fact_check.py's deliberate reuse of that
same key) since the YouTube Data API is commonly enabled on its own
GCP project with its own quota, and assuming they're the same project
would silently break this module for anyone who set them up
separately. Same empty-list-on-any-failure contract as the rest of
this project.
"""

import os
from typing import Dict, List, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

API_KEY_ENV = "YOUTUBE_API_KEY"
API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_NUM_RESULTS = 5


class YouTubeConnect:
    """YouTube Data API v3 search/metadata. Use get_youtube()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(API_KEY_ENV))

    def search(self, query: str, num: int = DEFAULT_NUM_RESULTS) -> List[Dict]:
        """Returns up to `num` matching videos as
        {"video_id": str, "title": str, "channel": str, "url": str}.
        Empty list on no backend, no query, or any request failure."""
        if not self.is_available() or not query:
            return []
        try:
            response = requests.get(
                f"{API_BASE}/search",
                params={
                    "key": os.environ[API_KEY_ENV],
                    "q": query,
                    "part": "snippet",
                    "type": "video",
                    "maxResults": max(1, min(num, 50)),
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            results = []
            for i in items:
                video_id = (i.get("id") or {}).get("videoId", "")
                snippet = i.get("snippet") or {}
                results.append(
                    {
                        "video_id": video_id,
                        "title": snippet.get("title", ""),
                        "channel": snippet.get("channelTitle", ""),
                        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                    }
                )
            return results
        except Exception:
            return []

    def video_details(self, video_id: str) -> Dict:
        """Returns {"title": str, "channel": str, "view_count": str,
        "duration": str} for `video_id`, or {} on no backend, no id,
        or any request failure (not the same as "video not found",
        which also returns {})."""
        if not self.is_available() or not video_id:
            return {}
        try:
            response = requests.get(
                f"{API_BASE}/videos",
                params={
                    "key": os.environ[API_KEY_ENV],
                    "id": video_id,
                    "part": "snippet,statistics,contentDetails",
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = response.json().get("items", [])
            if not items:
                return {}
            item = items[0]
            snippet = item.get("snippet") or {}
            statistics = item.get("statistics") or {}
            content_details = item.get("contentDetails") or {}
            return {
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "view_count": statistics.get("viewCount", ""),
                "duration": content_details.get("duration", ""),
            }
        except Exception:
            return {}


_youtube: Optional[YouTubeConnect] = None


def get_youtube() -> YouTubeConnect:
    global _youtube
    if _youtube is None:
        _youtube = YouTubeConnect()
    return _youtube
