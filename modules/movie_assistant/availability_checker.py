"""
Availability checker
=======================
Answers "where can I watch <movie>" for a given country.

Real path (TMDB_API_KEY configured): TMDB's official
`/movie/{id}/watch/providers` endpoint - a single free, no-extra-key
call that TMDB itself sources from JustWatch, covering flatrate
(subscription), rent, and buy options per country. No separate
JustWatch scraping/key needed.

Fallback path (no key, or the TMDB lookup fails): can't know real
availability, so instead of guessing, returns direct *search* links on
the major services (Netflix/Prime Video/Disney+ Hotstar/YouTube) for
the title - honest about the fact that it's a search link, not a
confirmed-available flag, via `"confirmed": False` on each entry.
"""

from typing import Dict, List, Optional
from urllib.parse import quote_plus

try:
    import requests as _requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import config
from modules.movie_assistant.movie_suggester import MovieSuggester

_TMDB_BASE = "https://api.themoviedb.org/3"

# Generic search-URL templates used when real provider data isn't
# available. Deliberately a small, well-known set rather than trying
# to guess every regional service. Public (no leading underscore) -
# auto_player.py imports this directly to know which platform names
# it can build a play URL for.
SEARCH_TEMPLATES = {
    "Netflix": "https://www.netflix.com/search?q={q}",
    "Prime Video": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={q}",
    "Disney+ Hotstar": "https://www.hotstar.com/in/search?q={q}",
    "YouTube": "https://www.youtube.com/results?search_query={q}",
}


class AvailabilityChecker:
    def __init__(self):
        self._api_key = getattr(config, "TMDB_API_KEY", None)
        self._suggester = MovieSuggester()

    def is_available(self) -> bool:
        return bool(self._api_key and HAS_REQUESTS)

    def check(self, movie_id: int, country: Optional[str] = None) -> Dict:
        """Real TMDB lookup by movie id. Returns
        {"success": True, "providers": [{"name", "type", "logo_url"}],
        "link": "<TMDB's own watch page for this movie/country>",
        "country": "IN"} or {"success": False, "error": "..."}."""
        country = country or getattr(config, "TMDB_DEFAULT_COUNTRY", "IN")
        if not self.is_available():
            return {"success": False, "error": "TMDB_API_KEY not configured"}
        try:
            resp = _requests.get(
                f"{_TMDB_BASE}/movie/{movie_id}/watch/providers",
                params={"api_key": self._api_key},
                timeout=8,
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"TMDB returned status {resp.status_code}"}
            data = resp.json().get("results", {}).get(country, {})
            if not data:
                return {
                    "success": True,
                    "providers": [],
                    "link": None,
                    "country": country,
                    "note": f"no listed streaming providers for this title in {country}",
                }
            providers: List[Dict] = []
            for kind in ("flatrate", "rent", "buy"):
                for p in data.get(kind, []):
                    providers.append(
                        {
                            "name": p.get("provider_name"),
                            "type": kind,
                            "logo_url": (
                                f"https://image.tmdb.org/t/p/w92{p['logo_path']}" if p.get("logo_path") else None
                            ),
                            "confirmed": True,
                        }
                    )
            return {"success": True, "providers": providers, "link": data.get("link"), "country": country}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_by_title(self, title: str, country: Optional[str] = None) -> Dict:
        """Resolves `title` to a TMDB id first, then check()s it. Falls
        back to generic search links (see module docstring) when TMDB
        isn't configured or the title can't be resolved."""
        if self.is_available():
            search = self._suggester.search_movie(title)
            if search.get("success"):
                movie_id = search["movie"]["id"]
                result = self.check(movie_id, country=country)
                if result.get("success"):
                    result["title"] = search["movie"]["title"]
                    result["movie_id"] = movie_id
                    if not result.get("providers"):
                        # Resolved the title fine, but TMDB has no
                        # provider data for this country - still more
                        # honest to fall through to search links than
                        # to report "nothing available".
                        return self._fallback_links(title, country, note=result.get("note"))
                    return result
        return self._fallback_links(title, country)

    def _fallback_links(self, title: str, country: Optional[str] = None, note: Optional[str] = None) -> Dict:
        q = quote_plus(title)
        providers = [
            {"name": name, "type": "search_link", "url": template.format(q=q), "confirmed": False}
            for name, template in SEARCH_TEMPLATES.items()
        ]
        return {
            "success": True,
            "title": title,
            "providers": providers,
            "country": country or getattr(config, "TMDB_DEFAULT_COUNTRY", "IN"),
            "note": note
            or "real availability unknown (TMDB_API_KEY not configured or title unresolved) - these are search links, not confirmed listings",
        }
