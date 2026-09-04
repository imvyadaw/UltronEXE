"""
Movie Assistant (Phase 27)
===========================
Mood/weather-aware movie recommendation pipeline:

    weather_integration.py  -> current weather -> a "viewing context"
    mood_analyzer.py        -> user's text (EN/Hinglish) -> a mood label
    movie_suggester.py      -> mood + weather -> ranked movie suggestions
                                (TMDB API when configured, curated
                                bilingual fallback lists when not)
    availability_checker.py -> a chosen movie -> which streaming
                                services actually have it (TMDB's
                                official watch/providers endpoint, or a
                                generic search-link fallback)
    auto_player.py          -> a chosen movie/platform -> actually opens
                                it (streaming service search page, or a
                                trailer via browser.chrome.youtube_play)

Every module follows the same convention as the rest of this codebase:
every public method returns a plain Dict, either
{"success": True, ...} or {"success": False, "error": "..."} (some
older-style modules return {"error": "..."} without "success" - callers
here check for the "error" key either way), and every module degrades
gracefully instead of raising when an optional API key isn't configured
(TMDB_API_KEY - see config.py) or a dependency (requests) is missing.

get_movie_assistant() returns a lazy singleton MovieAssistant facade
tying all five together for the common end-to-end flow: text/mood ->
suggestions -> availability -> play. Individual modules can also be
used standalone (e.g. just check_availability() for a movie the user
already named).
"""

from typing import Dict, Optional

from modules.movie_assistant.weather_integration import WeatherContext
from modules.movie_assistant.mood_analyzer import MoodAnalyzer
from modules.movie_assistant.movie_suggester import MovieSuggester
from modules.movie_assistant.availability_checker import AvailabilityChecker
from modules.movie_assistant.auto_player import AutoPlayer


class MovieAssistant:
    """Facade wiring weather + mood -> suggestions -> availability -> play."""

    def __init__(self):
        self.weather = WeatherContext()
        self.mood = MoodAnalyzer()
        self.suggester = MovieSuggester()
        self.availability = AvailabilityChecker()
        self.player = AutoPlayer()

    def recommend(
        self,
        text: str = "",
        mood: Optional[str] = None,
        location: str = "",
        language: str = "en",
        count: int = 5,
        use_weather: bool = True,
    ) -> Dict:
        """End-to-end: figure out the mood (from `mood` if given,
        otherwise analyzed from `text`), fold in weather context if
        requested, and return ranked suggestions. Returns
        {"success": True, "mood": {...}, "weather": {...}|None,
        "suggestions": [...]}."""
        mood_result = {"mood": mood, "confidence": 1.0, "source": "explicit"} if mood else self.mood.analyze(text)
        weather_result = None
        if use_weather:
            weather_result = self.weather.get_weather_mood(location)
            if not weather_result.get("success"):
                weather_result = None
        suggestions = self.suggester.suggest(
            mood=mood_result.get("mood"),
            weather_context=(weather_result or {}).get("viewing_context"),
            language=language,
            count=count,
        )
        return {
            "success": True,
            "mood": mood_result,
            "weather": weather_result,
            "suggestions": suggestions.get("results", []),
            "source": suggestions.get("source"),
        }

    def check_and_play(self, title: str, country: str = "IN", auto_play_trailer_if_unavailable: bool = True) -> Dict:
        """Checks where `title` is streaming, and plays it if a known
        platform can be launched straight to a search for it - falls
        back to a trailer if nothing is available and the caller
        allows it."""
        avail = self.availability.check_by_title(title, country=country)
        providers = avail.get("providers", []) if avail.get("success") else []
        if providers:
            play_result = self.player.play(title, platform=providers[0].get("name"))
            return {"success": True, "availability": avail, "played": play_result}
        if auto_play_trailer_if_unavailable:
            play_result = self.player.play_trailer(title)
            return {
                "success": True,
                "availability": avail,
                "played": play_result,
                "note": "not found on a streaming service - played trailer instead",
            }
        return {"success": True, "availability": avail, "played": None}


_instance: Optional[MovieAssistant] = None


def get_movie_assistant() -> MovieAssistant:
    global _instance
    if _instance is None:
        _instance = MovieAssistant()
    return _instance


__all__ = [
    "MovieAssistant",
    "get_movie_assistant",
    "WeatherContext",
    "MoodAnalyzer",
    "MovieSuggester",
    "AvailabilityChecker",
    "AutoPlayer",
]
