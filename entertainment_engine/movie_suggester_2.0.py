"""
Movie suggester 2.0
=====================
Upgrade layer over modules/movie_assistant/movie_suggester.py's
MovieSuggester - does NOT reimplement TMDB/fallback lookup, it wraps
it with two things the original class deliberately doesn't do:

  1. AI-router personalization: takes the raw candidate list
     MovieSuggester.suggest() already returns and asks the model
     (ai.ai_router.get_router().complete(), single-shot, no tools, no
     shared history - same guarantee ai/reasoning.py relies on) to
     rerank/annotate them against free-text context ("only Hindi
     movies", "nothing longer than 2 hours", "already seen Dangal")
     that a fixed genre-filter query can't express.
  2. movie_night_bundle(): pairs a movie pick with a matching mood
     playlist from entertainment_engine.mood_playlist, for a single
     "what should tonight look like" answer instead of two separate
     calls.

NOTE ON THIS FILE'S NAME: this file is intentionally named
"movie_suggester_2.0.py" (matching the requested tree exactly), but a
literal "." in a module filename is not valid in a Python `import`
statement (the "2" then "0" pieces would need to be separate valid
identifiers, and "0" isn't one). This file therefore cannot be reached
via `from entertainment_engine.movie_suggester_2.0 import ...` - it is
loaded by explicit file path (see entertainment_engine/__init__.py and
ai/supercharger_tools.py, both of which use importlib.util against
this exact path) rather than a normal dotted import.
"""

from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("movie_suggester_2_0")


def _base_suggester():
    from modules.movie_assistant.movie_suggester import MovieSuggester

    return MovieSuggester()


def suggest_movies_v2(
    mood: Optional[str] = None,
    weather_context: Optional[str] = None,
    language: str = "en",
    count: int = 5,
    preferences: Optional[str] = None,
) -> Dict:
    """Same base call as MovieSuggester.suggest(), plus an optional
    free-text `preferences` string ("Hindi only", "under 2 hours",
    "no horror") the model uses to rerank/filter/annotate the
    candidates. If `preferences` is omitted, or the model call fails
    for any reason, this returns the base suggester's result
    untouched - the AI layer is a strict improvement attempt, never a
    point of failure for the underlying feature."""
    base = _base_suggester().suggest(mood=mood, weather_context=weather_context, language=language, count=max(count, 5))
    if not preferences or not base.get("results"):
        base["personalized"] = False
        return base

    try:
        from ai.ai_router import get_router

        listing = "\n".join(
            f"{i + 1}. {r.get('title')} ({r.get('year')}) - {r.get('note') or r.get('overview') or ''}"
            for i, r in enumerate(base["results"])
        )
        prompt = (
            "Here is a list of candidate movies. Given the viewer's stated "
            f'preferences: "{preferences}", pick and reorder the best '
            f"{count} of them (drop ones that clearly conflict with the "
            "preferences). Reply with ONLY a comma-separated list of the "
            "chosen item numbers, best first, nothing else.\n\n"
            f"{listing}"
        )
        raw = get_router().complete(prompt, temperature=0.2, max_tokens=100).strip()
        indices = [int(tok.strip()) - 1 for tok in raw.replace(".", ",").split(",") if tok.strip().isdigit()]
        reranked = [base["results"][i] for i in indices if 0 <= i < len(base["results"])]
        if reranked:
            base["results"] = reranked[:count]
            base["personalized"] = True
        else:
            base["results"] = base["results"][:count]
            base["personalized"] = False
    except Exception as e:
        logger.info("suggest_movies_v2 personalization skipped: %s", e)
        base["results"] = base["results"][:count]
        base["personalized"] = False

    return base


def movie_night_bundle(
    mood: Optional[str] = None,
    text: Optional[str] = None,
    weather_context: Optional[str] = None,
    preferences: Optional[str] = None,
) -> Dict:
    """One-call "movie night" answer: a top movie pick + a matching
    mood playlist (for before/after the movie). `mood` wins if both
    `mood` and `text` are given; otherwise mood is detected from
    `text` the same way entertainment_engine.mood_playlist does."""
    from entertainment_engine.mood_playlist import suggest_playlist, _analyze_mood

    resolved_mood = mood or (_analyze_mood(text) if text else "neutral")
    movies = suggest_movies_v2(mood=resolved_mood, weather_context=weather_context, count=3, preferences=preferences)
    playlist = suggest_playlist(mood=resolved_mood, count=4)

    return {
        "success": True,
        "mood": resolved_mood,
        "top_movie": (movies.get("results") or [{}])[0],
        "more_movies": (movies.get("results") or [])[1:],
        "playlist": playlist.get("songs", []),
    }
