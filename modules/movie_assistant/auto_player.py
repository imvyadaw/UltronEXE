"""
Auto player
=============
Given a movie (and optionally a specific platform), actually opens it -
either the streaming service's search results for the title (fastest
real path: a full "click play" integration would need each platform's
own OAuth'd API, which is out of scope here, same call the project
already makes for Spotify's non-API fallback in apps/media/spotify.py),
or a trailer via browser.chrome.chrome.ChromeController.youtube_play()
(added this phase - see module docstring in that file) when no
platform is available/known.

Prefers going through windows.get_system_tools() (the same facade
core/executor.py uses for every other tool) so this reuses the same
Chrome-focus/youtube_play path already wired into the AI tool-calling
loop - but degrades to a plain webbrowser.open() call if that facade
can't be imported (e.g. running outside the full Windows dependency
set), same graceful-degradation convention as every other module here.
"""

import webbrowser
from typing import Dict, Optional
from urllib.parse import quote_plus

from modules.movie_assistant.availability_checker import SEARCH_TEMPLATES


def _get_system_tools():
    """Lazy import - windows/__init__.py pulls in the full Windows
    automation dependency stack (pywinauto, pygetwindow, groq, etc.),
    so this is only attempted at call time and only when actually
    needed, never at module import time."""
    try:
        from windows import get_system_tools

        return get_system_tools()
    except Exception:
        return None


class AutoPlayer:
    def play(self, title: str, platform: Optional[str] = None) -> Dict:
        """Opens `title` on `platform` if it's one of the known
        services (see availability_checker.py's _SEARCH_TEMPLATES),
        otherwise falls back to play_trailer(). Returns
        {"success": True, "platform": str, "url": str, "played_trailer": bool}
        or {"success": False, "error": "..."}."""
        if not title:
            return {"success": False, "error": "no title given"}
        if platform and platform in SEARCH_TEMPLATES:
            url = SEARCH_TEMPLATES[platform].format(q=quote_plus(title))
            try:
                webbrowser.open(url)
                return {"success": True, "platform": platform, "url": url, "played_trailer": False}
            except Exception as e:
                return {"success": False, "error": str(e)}
        # Unknown/unavailable platform - trailer is the one thing we
        # can always actually start playing.
        result = self.play_trailer(title)
        result["played_trailer"] = True
        return result

    def play_url(self, title: str, url: str) -> Dict:
        """Opens a specific URL already resolved by the caller (e.g.
        one of availability_checker.py's real TMDB provider links)."""
        if not url:
            return {"success": False, "error": "no url given"}
        try:
            webbrowser.open(url)
            return {"success": True, "title": title, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def play_trailer(self, title: str) -> Dict:
        """Actually starts playing `title`'s trailer on YouTube (not
        just opening search results) via youtube_play(). Returns
        {"success": True, "query": str, "video_id": str|None, "url": str}
        or {"success": False, "error": "..."}."""
        query = f"{title} official trailer"
        tools = _get_system_tools()
        if tools is not None:
            result = tools.youtube_play(query)
            if "error" not in result:
                return {"success": True, "query": query, **result}
            return {"success": False, "error": result["error"]}
        # Fallback: no windows facade available - open the search page
        # directly (won't auto-play, but never leaves the user with
        # nothing).
        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            webbrowser.open(url)
            return {
                "success": True,
                "query": query,
                "video_id": None,
                "url": url,
                "note": "opened search results only - couldn't auto-play (windows facade unavailable)",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
