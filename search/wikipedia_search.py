"""
Wikipedia Search
=================
Dedicated Wikipedia backend, separate from google_search.py's generic web
search. Every other module in SEARCH/ needs an API key from the caller's
own environment - this one deliberately doesn't, since Wikipedia's own
REST API (wikimedia.org, no auth) is free and unlimited for reasonable
use. Added because search_internet() (skills/internet/web_tools.py) was
relying on Wikipedia showing up incidentally in Google/DuckDuckGo results
- it often wouldn't, so factual "who is X" / "what is X" questions came
back thin or wrong even when Wikipedia had a clean, authoritative answer.

Two-step lookup, both plain HTTPS GET, no key:
  1. MediaWiki opensearch API - turns a loose query ("Salman Khan biwi")
     into the actual matching article title(s), same as typing into
     Wikipedia's own search box.
  2. Wikipedia REST API's page/summary/<title> endpoint - returns a clean
     plain-text extract (no wiki markup/citations/templates to strip) for
     that title.

Tries Hindi Wikipedia (hi.wikipedia.org) first when the query looks like
Hindi/Hinglish (reuses PHASE_18_4_VOICE_SYSTEM/EARS/hindi_english.py's
detector, same one voice/tts/tts_engine.py now uses), then falls back to
English Wikipedia if Hindi Wikipedia has no matching article - Hindi
Wikipedia's coverage is much thinner than English's, so a Hindi-phrased
question about, say, a Hollywood actor would otherwise come back empty
even though English Wikipedia has a full article.

Same contract as every other module in SEARCH/: no `requests` package, no
network, or any request failure all collapse to an empty/None result
rather than an exception.
"""

from typing import Dict, Optional

try:
    import requests

    _REQUESTS_AVAILABLE = True
except Exception:
    _REQUESTS_AVAILABLE = False

OPENSEARCH_ENDPOINT = "https://{lang}.wikipedia.org/w/api.php"
SUMMARY_ENDPOINT = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
DEFAULT_TIMEOUT_SECONDS = 3  # tight - this is now an extra hop tried before
# Google/DuckDuckGo, so a slow/hanging Wikipedia
# request shouldn't stall the whole reply. 3s is
# generous for Wikipedia's own fast API but cuts
# failover time in half versus the old 6s.


class WikipediaSearch:
    """Wikipedia-only lookup. Use get_wikipedia_search()."""

    def is_available(self) -> bool:
        return _REQUESTS_AVAILABLE

    def _detect_lang(self, query: str) -> str:
        """Returns \"hi\" if the query looks Hindi/Hinglish, else \"en\".
        Best-effort - the caller tries the other language too if this
        one comes back empty, so a wrong guess here just costs one
        extra request rather than a wrong/missing answer."""
        try:
            from ears.hindi_english import HindiEnglish

            label = HindiEnglish().detect(query)["label"]
            if label in ("hindi", "mixed"):
                return "hi"
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("search.wikipedia_search._detect_lang")
        return "en"

    def _find_title(self, query: str, lang: str) -> Optional[str]:
        """opensearch: query -> best-matching article title, or None."""
        try:
            response = requests.get(
                OPENSEARCH_ENDPOINT.format(lang=lang),
                params={
                    "action": "opensearch",
                    "search": query,
                    "limit": 1,
                    "namespace": 0,
                    "format": "json",
                },
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers={"User-Agent": "Ultron-Assistant/1.0"},
            )
            response.raise_for_status()
            data = response.json()
            titles = data[1] if len(data) > 1 else []
            return titles[0] if titles else None
        except Exception:
            return None

    def _get_summary(self, title: str, lang: str) -> Optional[Dict]:
        """REST summary endpoint for an already-known article title."""
        try:
            import urllib.parse

            response = requests.get(
                SUMMARY_ENDPOINT.format(lang=lang, title=urllib.parse.quote(title)),
                timeout=DEFAULT_TIMEOUT_SECONDS,
                headers={"User-Agent": "Ultron-Assistant/1.0"},
            )
            if response.status_code != 200:
                return None
            data = response.json()
            extract = data.get("extract")
            if not extract:
                return None
            return {
                "title": data.get("title", title),
                "extract": extract,
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                "lang": lang,
            }
        except Exception:
            return None

    def search(self, query: str) -> Optional[Dict]:
        """Returns {"title", "extract", "url", "lang"} for the best-
        matching Wikipedia article, or None if neither the guessed
        language nor the other one has one. `extract` is a clean plain-
        text summary (a few sentences to a short paragraph) - already
        speakable/printable with no further cleanup needed."""
        if not self.is_available() or not query:
            return None

        primary = self._detect_lang(query)
        fallback = "en" if primary == "hi" else "hi"

        for lang in (primary, fallback):
            title = self._find_title(query, lang)
            if not title:
                continue
            summary = self._get_summary(title, lang)
            if summary:
                return summary
        return None


_wikipedia_search: Optional[WikipediaSearch] = None


def get_wikipedia_search() -> WikipediaSearch:
    global _wikipedia_search
    if _wikipedia_search is None:
        _wikipedia_search = WikipediaSearch()
    return _wikipedia_search
