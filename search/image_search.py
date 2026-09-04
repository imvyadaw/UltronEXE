"""
Image Search
============
Same Google Custom Search JSON API as google_search.py, with
searchType=image - a separate module rather than a parameter on
GoogleSearch.search() because the result shape is different enough
(image_url + context page, not a text snippet) to deserve its own
return type, the same reasoning DISPLAY/face_label.py and
DISPLAY/price_tag.py stayed separate modules instead of one
"overlay.py" with a mode flag.

Same availability/degradation contract as google_search.py - same two
env vars, since both endpoints are the same Custom Search Engine, just
a different searchType.
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
MAX_NUM_RESULTS = 10


class ImageSearch:
    """Image search via Google Custom Search JSON API. Use get_image_search()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE and bool(os.environ.get(API_KEY_ENV)) and bool(os.environ.get(CSE_ID_ENV))

    def search(self, query: str, num: int = DEFAULT_NUM_RESULTS) -> List[Dict]:
        """Returns up to `num` results as
        {"title": str, "image_url": str, "context_url": str,
        "width": Optional[int], "height": Optional[int]}. Empty list
        on no backend, no query, or any request failure."""
        if not self.is_available() or not query:
            return []
        try:
            response = requests.get(
                ENDPOINT,
                params={
                    "key": os.environ[API_KEY_ENV],
                    "cx": os.environ[CSE_ID_ENV],
                    "q": query,
                    "searchType": "image",
                    "num": max(1, min(num, MAX_NUM_RESULTS)),
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            results = []
            for i in items:
                image_meta = i.get("image", {})
                results.append(
                    {
                        "title": i.get("title", ""),
                        "image_url": i.get("link", ""),
                        "context_url": image_meta.get("contextLink", ""),
                        "width": image_meta.get("width"),
                        "height": image_meta.get("height"),
                    }
                )
            return results
        except Exception:
            return []


_image_search: Optional[ImageSearch] = None


def get_image_search() -> ImageSearch:
    global _image_search
    if _image_search is None:
        _image_search = ImageSearch()
    return _image_search
