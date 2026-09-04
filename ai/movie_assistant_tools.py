"""
Movie assistant tool registry (Phase 27)
===========================================
Wires modules/movie_assistant/ into the same tool-calling loop as every
other Ultron tool, following the exact pattern ai/new_skills_tools.py
established: a lazy module-level singleton, name -> lambda handlers in
MOVIE_ASSISTANT_DIRECT_HANDLERS (merged into ai/tool_runtime.py's
_DIRECT_HANDLERS), and MOVIE_ASSISTANT_TOOLS (merged into
ai/tools_schema.py's TOOLS) using the identical duplicated `_tool()`
helper (see new_skills_tools.py's docstring for why it's duplicated
rather than imported - same circular-import reason applies here).
"""


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


_assistant = None


def _get_assistant():
    global _assistant
    if _assistant is None:
        from modules.movie_assistant import get_movie_assistant

        _assistant = get_movie_assistant()
    return _assistant


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
MOVIE_ASSISTANT_DIRECT_HANDLERS = {
    "analyze_mood": lambda d: _get_assistant().mood.analyze(d.get("text", "")),
    "suggest_movie": lambda d: _get_assistant().recommend(
        text=d.get("text", ""),
        mood=d.get("mood"),
        location=d.get("location", ""),
        language=d.get("language", "en"),
        count=d.get("count", 5),
        use_weather=d.get("use_weather", True),
    ),
    "check_movie_availability": lambda d: _get_assistant().availability.check_by_title(
        d.get("title", ""), country=d.get("country")
    ),
    "play_movie": lambda d: _get_assistant().player.play(d.get("title", ""), platform=d.get("platform")),
    "play_movie_trailer": lambda d: _get_assistant().player.play_trailer(d.get("title", "")),
    "recommend_and_play_movie": lambda d: _get_assistant().check_and_play(
        d.get("title", ""), country=d.get("country", "IN")
    ),
}


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
MOVIE_ASSISTANT_TOOLS = [
    _tool(
        "analyze_mood",
        "Detect the user's current mood from their message (English or "
        "Hinglish) - happy, sad, stressed, bored, romantic, adventurous, "
        "nostalgic, angry, relaxed, or scared. Use before suggest_movie "
        "when the user hasn't stated a mood directly, to ground the "
        "recommendation in what they actually said.",
        {"text": {"type": "string", "description": "The user's message to analyze."}},
        ["text"],
    ),
    _tool(
        "suggest_movie",
        "Suggest movies based on mood and (optionally) current weather - "
        "e.g. 'suggest a movie', 'mood ke hisaab se movie batao', 'bore ho "
        "raha hu kuch dikha do'. Pass `mood` directly if already known "
        "(e.g. from analyze_mood or the user stated it), otherwise pass "
        "`text` and it will be analyzed. Weather is factored in by default "
        "(set use_weather=false to skip it).",
        {
            "text": {"type": "string", "description": "User's message, used to detect mood if `mood` isn't given."},
            "mood": {"type": "string", "description": "Mood to suggest for, if already known (skips text analysis)."},
            "location": {"type": "string", "description": "Location for weather context. Blank = auto-detect by IP."},
            "language": {"type": "string", "description": "Preferred language code, e.g. 'en' or 'hi'. Default 'en'."},
            "count": {"type": "integer", "description": "How many suggestions to return. Default 5."},
            "use_weather": {"type": "boolean", "description": "Whether to factor in current weather. Default true."},
        },
        [],
    ),
    _tool(
        "check_movie_availability",
        "Check which streaming service(s) a specific movie is available "
        "on - e.g. 'is <movie> on Netflix?', '<movie> kahan dekhu'.",
        {
            "title": {"type": "string", "description": "The movie title to check."},
            "country": {
                "type": "string",
                "description": "Country code for regional availability, e.g. 'IN', 'US'. Defaults to the configured default.",
            },
        },
        ["title"],
    ),
    _tool(
        "play_movie",
        "Open/start playing a specific movie - e.g. 'play <movie>', "
        "'<movie> chala do'. Opens the given platform's search for the "
        "title if `platform` is a known service (Netflix, Prime Video, "
        "Disney+ Hotstar, YouTube); otherwise plays the trailer on "
        "YouTube directly as the best available fallback.",
        {
            "title": {"type": "string", "description": "The movie title to play."},
            "platform": {"type": "string", "description": "Preferred streaming platform, if known (e.g. 'Netflix')."},
        },
        ["title"],
    ),
    _tool(
        "play_movie_trailer",
        "Play a movie's official trailer on YouTube - actual playback "
        "starts, not just a search page. Use when the user just wants a "
        "quick trailer rather than the full movie.",
        {"title": {"type": "string", "description": "The movie title whose trailer to play."}},
        ["title"],
    ),
    _tool(
        "recommend_and_play_movie",
        "One-shot: check where `title` is available and immediately play "
        "it there, or play its trailer if it isn't available anywhere "
        "known - e.g. 'find and play <movie>'.",
        {
            "title": {"type": "string", "description": "The movie title to find and play."},
            "country": {"type": "string", "description": "Country code for availability. Default 'IN'."},
        },
        ["title"],
    ),
]
