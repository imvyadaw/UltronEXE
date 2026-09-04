"""
Movie suggester
==================
Turns a mood (from mood_analyzer.py) + optional weather viewing-context
(from weather_integration.py) into ranked movie suggestions.

Two backends, same {"success": True, "results": [...], "source": "..."}
shape either way:

  - TMDB (config.TMDB_API_KEY set): real, current data via the public
    /discover/movie endpoint, genre-filtered from _MOOD_GENRES below and
    sorted by popularity. requests-based, same dependency the rest of
    this codebase already uses (skills/internet/weather.py etc).
  - Curated fallback (no key, or the TMDB call fails/network is down):
    a small static bilingual (Hollywood + Bollywood) list per mood in
    _FALLBACK_SUGGESTIONS, so the feature still works with zero setup.
    Not meant to be exhaustive - it's a "never return nothing" safety
    net, not a competitor to a real catalog.

Neither backend needs a movie's TMDB ID to already be known by the
caller - search_movie() is provided separately for when the caller
already has a title in hand (e.g. availability_checker.py needing to
resolve a title to a TMDB id) rather than asking for a fresh
suggestion.
"""

from typing import Dict, List, Optional

try:
    import requests as _requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

import config

_TMDB_BASE = "https://api.themoviedb.org/3"

# Standard TMDB movie genre IDs (https://api.themoviedb.org/3/genre/movie/list)
_GENRE = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "scifi": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}

# mood -> ordered genre preference (first = strongest lean). For "sad"
# and "stressed" this deliberately leans toward uplifting genres
# (comedy/family) rather than mirroring the mood with more drama - a
# mood-lifting pick is generally what's wanted for "what should I
# watch" rather than a mood-matching one.
_MOOD_GENRES: Dict[str, List[str]] = {
    "happy": ["comedy", "family", "animation"],
    "sad": ["comedy", "family", "drama"],
    "stressed": ["comedy", "family", "animation"],
    "bored": ["action", "adventure", "thriller"],
    "romantic": ["romance", "drama"],
    "adventurous": ["adventure", "action", "fantasy"],
    "nostalgic": ["family", "animation", "music"],
    "angry": ["comedy", "action"],
    "relaxed": ["drama", "documentary", "romance"],
    "scared": ["horror", "thriller", "mystery"],
    "neutral": [],
}

# weather viewing_context -> a genre to fold in alongside the mood's
# own list (deduped, appended after the mood genres so mood always
# takes priority over weather).
_WEATHER_GENRES: Dict[str, str] = {
    "rainy": "romance",
    "stormy": "thriller",
    "snowy": "family",
    "foggy": "mystery",
    "cloudy": "drama",
    "sunny": "comedy",
    "hot": "action",
    "cold": "family",
    "neutral": "",
}

_FALLBACK_SUGGESTIONS: Dict[str, List[Dict]] = {
    "happy": [
        {"title": "The Grand Budapest Hotel", "year": 2014, "note": "whimsical, colorful comedy"},
        {"title": "Zindagi Na Milegi Dobara", "year": 2011, "note": "feel-good friendship road trip"},
        {"title": "Paddington 2", "year": 2017, "note": "warm, universally loved comedy"},
    ],
    "sad": [
        {"title": "Chhichhore", "year": 2019, "note": "nostalgic, ultimately uplifting"},
        {"title": "School of Rock", "year": 2003, "note": "light, energetic comedy"},
        {"title": "Amelie", "year": 2001, "note": "gentle, heartwarming"},
    ],
    "stressed": [
        {"title": "Kung Fu Panda", "year": 2008, "note": "easy, funny, low-stakes"},
        {"title": "The Intouchables", "year": 2011, "note": "warm, funny, uplifting"},
        {"title": "Chef", "year": 2014, "note": "breezy comfort watch"},
    ],
    "bored": [
        {"title": "Mad Max: Fury Road", "year": 2015, "note": "high-octane action"},
        {"title": "Dangal", "year": 2016, "note": "gripping underdog sports drama"},
        {"title": "Mission: Impossible - Fallout", "year": 2018, "note": "non-stop thriller"},
    ],
    "romantic": [
        {"title": "Jab We Met", "year": 2007, "note": "classic Bollywood romance"},
        {"title": "La La Land", "year": 2016, "note": "romantic musical drama"},
        {"title": "Before Sunrise", "year": 1995, "note": "intimate slow-burn romance"},
    ],
    "adventurous": [
        {"title": "Indiana Jones and the Raiders of the Lost Ark", "year": 1981, "note": "classic adventure"},
        {"title": "Zindagi Na Milegi Dobara", "year": 2011, "note": "adventure + self-discovery"},
        {"title": "Interstellar", "year": 2014, "note": "epic sci-fi adventure"},
    ],
    "nostalgic": [
        {"title": "Taare Zameen Par", "year": 2007, "note": "warm, childhood-themed drama"},
        {"title": "Toy Story", "year": 1995, "note": "timeless animated classic"},
        {"title": "Kabhi Khushi Kabhie Gham", "year": 2001, "note": "classic family drama"},
    ],
    "angry": [
        {"title": "John Wick", "year": 2014, "note": "cathartic action"},
        {"title": "The Nice Guys", "year": 2016, "note": "action-comedy release valve"},
    ],
    "relaxed": [
        {"title": "Lost in Translation", "year": 2003, "note": "slow, atmospheric"},
        {"title": "The Lunchbox", "year": 2013, "note": "gentle, quiet drama"},
        {"title": "Julie & Julia", "year": 2009, "note": "cozy, easy watch"},
    ],
    "scared": [
        {"title": "Hereditary", "year": 2018, "note": "modern horror"},
        {"title": "Tumbbad", "year": 2018, "note": "acclaimed Indian horror-folklore"},
        {"title": "Get Out", "year": 2017, "note": "horror-thriller"},
    ],
    "neutral": [
        {"title": "Inception", "year": 2010, "note": "broadly popular, works for any mood"},
        {"title": "3 Idiots", "year": 2009, "note": "broadly loved, works for any mood"},
        {"title": "The Dark Knight", "year": 2008, "note": "broadly popular"},
    ],
}


class MovieSuggester:
    def __init__(self):
        self._api_key = getattr(config, "TMDB_API_KEY", None)

    def is_available(self) -> bool:
        return bool(self._api_key and HAS_REQUESTS)

    def _genres_for(self, mood: Optional[str], weather_context: Optional[str]) -> List[str]:
        genres = list(_MOOD_GENRES.get(mood or "neutral", []))
        weather_genre = _WEATHER_GENRES.get(weather_context or "", "")
        if weather_genre and weather_genre not in genres:
            genres.append(weather_genre)
        return genres

    def suggest(
        self,
        mood: Optional[str] = None,
        weather_context: Optional[str] = None,
        language: str = "en",
        count: int = 5,
    ) -> Dict:
        """Returns {"success": True, "results": [...], "source": "tmdb"|"fallback",
        "genres_used": [...]}. `results` items always have at least
        title/year/note (TMDB results add id/overview/rating/poster_url)."""
        genres = self._genres_for(mood, weather_context)
        if self.is_available():
            tmdb_result = self._suggest_via_tmdb(genres, language, count)
            if tmdb_result is not None:
                return {"success": True, "results": tmdb_result, "source": "tmdb", "genres_used": genres}
        # Fallback: no key, requests missing, or the TMDB call failed.
        fallback = _FALLBACK_SUGGESTIONS.get(mood or "neutral", _FALLBACK_SUGGESTIONS["neutral"])
        return {"success": True, "results": fallback[:count], "source": "fallback", "genres_used": genres}

    def _suggest_via_tmdb(self, genres: List[str], language: str, count: int) -> Optional[List[Dict]]:
        genre_ids = ",".join(str(_GENRE[g]) for g in genres if g in _GENRE)
        params = {
            "api_key": self._api_key,
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "language": f"{language}-US" if language == "en" else language,
            "vote_count.gte": 50,
        }
        if genre_ids:
            params["with_genres"] = genre_ids
        try:
            resp = _requests.get(f"{_TMDB_BASE}/discover/movie", params=params, timeout=8)
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = []
            for movie in data.get("results", [])[:count]:
                results.append(
                    {
                        "id": movie.get("id"),
                        "title": movie.get("title"),
                        "year": (movie.get("release_date") or "")[:4],
                        "rating": movie.get("vote_average"),
                        "overview": movie.get("overview"),
                        "poster_url": (
                            f"https://image.tmdb.org/t/p/w342{movie['poster_path']}"
                            if movie.get("poster_path")
                            else None
                        ),
                    }
                )
            return results
        except Exception:
            return None

    def search_movie(self, title: str) -> Dict:
        """Resolve a plain title to TMDB's best-match record (id needed
        by availability_checker.py). Returns
        {"success": True, "movie": {...}} or {"success": False, "error": ...}."""
        if not self.is_available():
            return {"success": False, "error": "TMDB_API_KEY not configured"}
        try:
            resp = _requests.get(
                f"{_TMDB_BASE}/search/movie",
                params={"api_key": self._api_key, "query": title, "include_adult": "false"},
                timeout=8,
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"TMDB returned status {resp.status_code}"}
            results = resp.json().get("results", [])
            if not results:
                return {"success": False, "error": f"no TMDB match found for '{title}'"}
            best = results[0]
            return {
                "success": True,
                "movie": {
                    "id": best.get("id"),
                    "title": best.get("title"),
                    "year": (best.get("release_date") or "")[:4],
                    "overview": best.get("overview"),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
