"""
Mood playlist
=============
Music-suggestion sibling to modules/movie_assistant/movie_suggester.py.
Reuses modules.movie_assistant.mood_analyzer.MoodAnalyzer for mood
detection (same mood taxonomy: happy/sad/stressed/bored/romantic/
adventurous/nostalgic/angry/relaxed/scared/neutral) instead of a
second mood classifier, so "mood" means the same thing everywhere in
the codebase.

No streaming-service API key/SDK is bundled anywhere in this codebase
(no Spotify/YT Music client exists to reuse), so this is a curated
static playlist per mood - same "never return nothing" fallback
philosophy as movie_suggester.py's _FALLBACK_SUGGESTIONS, just without
a TMDB-equivalent live backend to prefer first. Each entry is a
song + artist the assistant can hand off to open_url/search_internet
tools elsewhere if the caller wants to actually play it - this module
only decides WHAT to suggest, not how to play it (matches
modules/movie_assistant/auto_player.py's separation of concerns).
"""

from typing import Dict, List, Optional

_PLAYLISTS: Dict[str, List[Dict]] = {
    "happy": [
        {"title": "Happy", "artist": "Pharrell Williams"},
        {"title": "Badtameez Dil", "artist": "Benny Dayal"},
        {"title": "Uptown Funk", "artist": "Mark Ronson ft. Bruno Mars"},
        {"title": "London Thumakda", "artist": "Labh Janjua, Sonu Kakkar"},
    ],
    "sad": [
        {"title": "Someone Like You", "artist": "Adele"},
        {"title": "Channa Mereya", "artist": "Arijit Singh"},
        {"title": "Fix You", "artist": "Coldplay"},
        {"title": "Tum Hi Ho", "artist": "Arijit Singh"},
    ],
    "stressed": [
        {"title": "Weightless", "artist": "Marconi Union"},
        {"title": "Kun Faya Kun", "artist": "A.R. Rahman"},
        {"title": "Breathe Me", "artist": "Sia"},
        {"title": "Iktara", "artist": "Amit Trivedi"},
    ],
    "bored": [
        {"title": "Can't Stop the Feeling!", "artist": "Justin Timberlake"},
        {"title": "Malhari", "artist": "Vishal Dadlani"},
        {"title": "Levitating", "artist": "Dua Lipa"},
        {"title": "Kar Gayi Chull", "artist": "Badshah, Fazilpuria"},
    ],
    "romantic": [
        {"title": "Perfect", "artist": "Ed Sheeran"},
        {"title": "Tum Se Hi", "artist": "Mohit Chauhan"},
        {"title": "All of Me", "artist": "John Legend"},
        {"title": "Raabta", "artist": "Arijit Singh"},
    ],
    "adventurous": [
        {"title": "Kar Har Maidaan Fateh", "artist": "Sukhwinder Singh"},
        {"title": "Thunderstruck", "artist": "AC/DC"},
        {"title": "Zinda", "artist": "Siddharth Mahadevan"},
        {"title": "Centuries", "artist": "Fall Out Boy"},
    ],
    "nostalgic": [
        {"title": "Yeh Jawaani Hai Deewani (Title Track)", "artist": "Pritam"},
        {"title": "Yesterday", "artist": "The Beatles"},
        {"title": "Abhi Mujh Mein Kahin", "artist": "Sonu Nigam"},
        {"title": "Vienna", "artist": "Billy Joel"},
    ],
    "angry": [
        {"title": "Numb", "artist": "Linkin Park"},
        {"title": "Angaaray", "artist": "Vishal-Shekhar"},
        {"title": "Break Stuff", "artist": "Limp Bizkit"},
    ],
    "relaxed": [
        {"title": "Weightless (Reprise)", "artist": "Marconi Union"},
        {"title": "Tum Se Hi (Acoustic)", "artist": "Mohit Chauhan"},
        {"title": "River Flows in You", "artist": "Yiruma"},
    ],
    "scared": [
        {"title": "Thriller", "artist": "Michael Jackson"},
        {"title": "Bhoot Hoon Main", "artist": "Amit Trivedi"},
    ],
    "neutral": [
        {"title": "Blinding Lights", "artist": "The Weeknd"},
        {"title": "Kesariya", "artist": "Arijit Singh"},
        {"title": "Shape of You", "artist": "Ed Sheeran"},
    ],
}


def _analyze_mood(text: str) -> str:
    try:
        from modules.movie_assistant.mood_analyzer import MoodAnalyzer

        return MoodAnalyzer().analyze(text).get("mood", "neutral")
    except Exception:
        return "neutral"


def suggest_playlist(mood: Optional[str] = None, text: Optional[str] = None, count: int = 5) -> Dict:
    """Suggest a mood-based playlist. Pass either an already-known
    `mood` (one of _PLAYLISTS' keys) or free `text` to have it
    detected via mood_analyzer.py - `mood` wins if both are given.
    Returns {"success": True, "mood": str, "songs": [...]}."""
    if not mood and text:
        mood = _analyze_mood(text)
    mood = (mood or "neutral").lower()
    songs = _PLAYLISTS.get(mood, _PLAYLISTS["neutral"])
    return {"success": True, "mood": mood, "songs": songs[:count]}
