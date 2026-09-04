"""
Entertainment engine
=====================
Complements modules/movie_assistant/ (which already owns mood
detection + movie suggestions + availability + weather context)
instead of duplicating it:

  - mood_playlist.py: same mood taxonomy as
    modules/movie_assistant/mood_analyzer.py, but for music - reuses
    that mood_analyzer for mood detection rather than a second copy.
  - movie_suggester_2.0.py: wraps the existing
    modules.movie_assistant.movie_suggester.MovieSuggester with an
    AI-router reranking/personalization pass and a combined
    "movie night" bundle (movie + matching playlist) on top.

movie_suggester_2.0.py is loaded here via importlib against its exact
file path rather than a normal `from . import` - see that file's own
docstring for why a literal "." in a module filename can't be reached
with a dotted import statement.
"""

import importlib.util as _ilu
import os as _os

from entertainment_engine.mood_playlist import suggest_playlist

_spec = _ilu.spec_from_file_location(
    "entertainment_engine._movie_suggester_2_0",
    _os.path.join(_os.path.dirname(__file__), "movie_suggester_2.0.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

suggest_movies_v2 = _mod.suggest_movies_v2
movie_night_bundle = _mod.movie_night_bundle

__all__ = ["suggest_playlist", "suggest_movies_v2", "movie_night_bundle"]
