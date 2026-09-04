"""
Weather integration for the movie assistant
=============================================
Reuses the existing skills/internet/weather.py WeatherLookup (wttr.in,
no API key needed) rather than adding a second weather backend, and
adds one thing on top: mapping the raw weather text to a small
"viewing_context" tag that movie_suggester.py can turn into a genre
lean - e.g. rainy/cold nights lean toward cozy comfort-watches, hot
sunny afternoons lean toward light/energetic picks, clear nights lean
toward anything including thrillers/horror.

This is deliberately a keyword heuristic, not a weather-condition
taxonomy - wttr.in's ?format=3 output is a short human-readable string
("London: 🌦️ +14°C"), not structured JSON, so exact condition codes
aren't available without switching backends. Good enough for a "what
should I watch" nudge; never blocks a suggestion if it can't classify.
"""

import re
from typing import Dict

from skills.internet.weather import WeatherLookup

# Ordered so more specific conditions are checked before generic ones
# (e.g. "thunderstorm" before "rain"). Each entry: (regex, viewing_context).
_CONDITION_RULES = [
    (r"thunder|storm", "stormy"),
    (r"snow|blizzard|sleet", "snowy"),
    (r"rain|drizzle|shower", "rainy"),
    (r"fog|mist|haze", "foggy"),
    (r"cloud|overcast", "cloudy"),
    (r"clear|sunny|sun\b", "sunny"),
]

# viewing_context -> a short human-readable note + genre lean, consumed
# by movie_suggester.py's _WEATHER_GENRE_MAP. Kept here (not duplicated
# there) so the two stay in sync - movie_suggester.py imports the keys
# from this module's VIEWING_CONTEXTS rather than hardcoding its own list.
VIEWING_CONTEXTS = {
    "rainy": "cozy, comfort-watch weather - a rainy-day movie or a warm rom-com/drama fits well",
    "stormy": "dramatic weather - a good night for an intense thriller or a cozy family film indoors",
    "snowy": "snowed-in weather - classic comfort-watch or holiday-movie territory",
    "foggy": "moody weather - atmospheric mysteries or noir-ish thrillers fit the mood",
    "cloudy": "mellow weather - fine for most genres, slight lean toward relaxed drama/comedy",
    "sunny": "bright, energetic weather - light comedies or feel-good adventure fit better than heavy drama",
    "hot": "hot weather - light, easy-watch comedy or action over anything heavy",
    "cold": "cold weather - cozy comfort-watch or a warm feel-good pick",
    "neutral": "no strong weather lean - open to any genre",
}


def _classify(weather_text: str) -> str:
    text = weather_text.lower()
    for pattern, tag in _CONDITION_RULES:
        if re.search(pattern, text):
            return tag
    # No condition keyword matched - fall back to temperature if present.
    temp_match = re.search(r"([+-]?\d+)\s*°?c", text)
    if temp_match:
        temp_c = int(temp_match.group(1))
        if temp_c >= 32:
            return "hot"
        if temp_c <= 10:
            return "cold"
    return "neutral"


class WeatherContext:
    """Wraps WeatherLookup and adds a viewing-context classification."""

    def __init__(self):
        self._lookup = WeatherLookup()

    def get_weather_mood(self, location: str = "") -> Dict:
        """Returns {"success": True, "weather": "<raw wttr.in string>",
        "viewing_context": "<tag>", "note": "<human-readable lean>"} or
        {"success": False, "error": "..."} if the weather lookup
        itself failed (offline, requests missing, service down)."""
        result = self._lookup.get_weather(location)
        if "error" in result:
            return {"success": False, "error": result["error"]}
        weather_text = result.get("weather", "")
        context = _classify(weather_text)
        return {
            "success": True,
            "weather": weather_text,
            "viewing_context": context,
            "note": VIEWING_CONTEXTS.get(context, VIEWING_CONTEXTS["neutral"]),
        }
