"""
Web tools
=========
search_internet(): now three-tier. Wikipedia (PHASE_18_5_SEARCH_ENGINE/
SEARCH/wikipedia_search.py, no key needed) is tried FIRST for factual/
biographical/definitional queries, since a clean Wikipedia summary beats
a scraped snippet and used to only show up in results by chance. Falls
back to Google Custom Search (PHASE_18_5_SEARCH_ENGINE/SEARCH/
google_search.py) when GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_CSE_ID are
configured, then to the DuckDuckGo-Lite scraper below when neither of
those apply or return anything - so this tool always works with zero
setup, but gets meaningfully better results the moment real API keys are
added. See .env.template for the two env vars.

read_url(): readable-text extraction from any URL.

Speed notes (fixed - was the main cause of slow search responses):
  - A single requests.Session is reused across calls instead of opening a
    fresh TCP+TLS connection every time (connection pooling / keep-alive).
  - Timeouts are tightened (10s -> 6s) so one unresponsive site can't stall
    a whole research pass anywhere near as long.
  - read_url() now streams the response and stops after a capped number of
    bytes (READ_URL_MAX_BYTES) instead of downloading the entire page (some
    pages are multiple MB) before throwing most of it away during the
    later 8000-char truncation. Big win on large/slow pages.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict
import re

from search.google_search import get_google_search
from search.wikipedia_search import get_wikipedia_search

SEARCH_TIMEOUT_SECONDS = 6
READ_URL_TIMEOUT_SECONDS = 6
READ_URL_MAX_BYTES = 400_000  # stop downloading a page past ~400KB of raw HTML

# Query patterns that mean "don't bother trying Wikipedia" - time-sensitive/
# live data Wikipedia never has (weather, prices, scores, breaking news,
# "today/abhi/aaj/latest"). Without this gate, EVERY query paid Wikipedia's
# 1-4 extra HTTP round trips first even when it could never have an answer,
# which slowed down exactly the queries where speed matters most (a live
# score or today's weather). Checked as whole-word substrings, case-
# insensitive, English + common Hindi/Hinglish terms.
_SKIP_WIKIPEDIA_PATTERNS = re.compile(
    r"\b("
    r"weather|mausam|temperature|forecast|rain|barish|"
    r"price|kimat|qeemat|stock|share price|"
    r"score|live score|match|cricket score|"
    r"news|khabar|breaking|"
    r"today|aaj|abhi|right now|abhi ka|"
    r"latest|current|kal ka"
    r")\b",
    re.IGNORECASE,
)


def _should_try_wikipedia(query: str) -> bool:
    return not _SKIP_WIKIPEDIA_PATTERNS.search(query or "")


class WebTools:
    """Tools for accessing the internet."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        # Reused across every search_internet()/read_url() call on this
        # instance so repeated requests (e.g. several sources in one
        # research pass) don't pay a fresh connection setup cost each time.
        self._session = requests.Session()
        self._session.headers.update(self.headers)

    def search_internet(self, query: str, num_results: int = 5) -> Dict:
        """Search the internet for a query. Tries Wikipedia first (best
        for "who is X" / "what is X" / biographical / definitional
        queries - a clean authoritative summary, no key needed) UNLESS
        the query looks time-sensitive (weather/price/score/news/today -
        see _SKIP_WIKIPEDIA_PATTERNS), since Wikipedia can never answer
        those and trying anyway just adds latency before the real
        answer comes from Google/DuckDuckGo below. Falls back to Google
        Custom Search (real API, needs GOOGLE_SEARCH_API_KEY +
        GOOGLE_SEARCH_CSE_ID - see .env.template); if that's not
        configured, or the call fails, or it comes back with zero
        results, falls back to the DuckDuckGo Lite scraper so this still
        works with no API keys at all.
        Returns a list of results with title and URL."""
        wikipedia = get_wikipedia_search()
        if _should_try_wikipedia(query) and wikipedia.is_available():
            try:
                hit = wikipedia.search(query)
                if hit:
                    return {
                        "success": True,
                        "source": "wikipedia",
                        "results": [{"title": hit["title"], "url": hit["url"], "description": hit["extract"]}],
                        "count": 1,
                    }
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("skills.internet.web_tools.search_internet")

        google = get_google_search()
        if google.is_available():
            try:
                items = google.search(query, num=num_results)
                if items:
                    return {
                        "success": True,
                        "source": "google_custom_search",
                        "results": [{"title": i["title"], "url": i["url"], "description": i["snippet"]} for i in items],
                        "count": len(items),
                    }
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("skills.internet.web_tools.search_internet")

        result = self._search_duckduckgo(query, num_results)
        if result.get("success"):
            return result

        # Every live tier failed (most likely: genuinely no internet
        # connection - Wikipedia API, Google CSE, and a plain HTTPS POST
        # to DuckDuckGo all errored out). Last resort: the local offline
        # knowledge base, if the user has built one and enabled it (see
        # knowledge_base/offline_wiki/ - off by default, ULTRON_OFFLINE_KB_ENABLED).
        # This deliberately does NOT replace result - if the offline KB
        # also has nothing, the original (informative) failure reason from
        # DuckDuckGo is what gets returned, not a generic offline error.
        try:
            from knowledge_base.offline_wiki import search_offline

            offline_result = search_offline(query, top_k=num_results)
            if offline_result.get("success"):
                return offline_result
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("skills.internet.web_tools.search_internet.offline_fallback")

        return result

    def _search_duckduckgo(self, query: str, num_results: int = 5) -> Dict:
        """Fallback backend: DuckDuckGo Lite (scraper, no API key needed).
        Returns a list of results with title and URL."""
        try:
            url = "https://lite.duckduckgo.com/lite/"
            data = {"q": query}

            response = self._session.post(url, data=data, timeout=SEARCH_TIMEOUT_SECONDS)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            results = []

            links = soup.select(".result-link")
            snippets = soup.select(".result-snippet")

            for i, link in enumerate(links):
                if len(results) >= num_results:
                    break

                href = link.get("href")
                title = link.get_text()

                if not href or "duckduckgo.com" in href:
                    continue

                snippet = snippets[i].get_text().strip() if i < len(snippets) else ""

                results.append({"title": title, "url": href, "description": snippet})

            return {"success": True, "source": "duckduckgo_lite", "results": results, "count": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_url(self, url: str) -> Dict:
        """Read the content of a specific URL. Extracts main text content.
        Streams the download and stops after READ_URL_MAX_BYTES, since we
        only ever keep the first 8000 chars of extracted text anyway -
        no point pulling down an entire multi-MB page for that."""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            response = self._session.get(url, timeout=READ_URL_TIMEOUT_SECONDS, stream=True)
            response.raise_for_status()

            raw = bytearray()
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                raw.extend(chunk)
                if len(raw) >= READ_URL_MAX_BYTES:
                    break
            response.close()

            soup = BeautifulSoup(bytes(raw), "html.parser")

            for script in soup(["script", "style", "nav", "footer", "header", "form"]):
                script.decompose()

            text = soup.get_text()

            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            truncated = len(text) > 8000
            content = text[:8000] + ("...\n[Content truncated]" if truncated else "")

            return {
                "success": True,
                "url": url,
                "title": soup.title.string if soup.title else "No Title",
                "content": content,
                "length": len(content),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
