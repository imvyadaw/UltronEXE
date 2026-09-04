"""
Image display tool - "show me a photo of X"
=============================================
Wires a `show_image` tool that:
  1. Looks up a REAL photo for whatever the user asked about.
     Primary source: Wikipedia's REST summary API (thumbnail field,
     which is always a real, licensed photo/illustration from that
     article - never an AI-generated or stock placeholder image).
     Fallback source (only tried if Wikipedia has no article, no
     thumbnail, or is unreachable): the existing Google Custom Search
     image backend (search/image_search.py, already used elsewhere for
     reverse-image/visual lookups) - still a real photo returned by a
     search engine, never generated. This matters in practice for
     regional/Bhojpuri/Indian-language figures (e.g. "Khesari Lal Yadav")
     who often don't have an infobox photo on Wikipedia even when they
     have a well-photographed public presence elsewhere.
  2. Emits it on the shared core.events bus as "image_ready" - the same
     bus core/assistant.py already emits turn/tool/state events on -
     which ui/web_dashboard/app.py relays to the browser over the
     existing SSE stream, and ui/web_dashboard's dashboard.js renders in
     a new image panel. Nothing about the dashboard's transport had to
     change; this only adds one more event type onto it.

If neither source has a real photo (or the fallback isn't configured -
GOOGLE_SEARCH_API_KEY/GOOGLE_SEARCH_CSE_ID unset), this returns
success=False with a clear reason - it does NOT fall back to generating
or guessing an image. The model should tell the user no verified photo
was found rather than claim it showed one.
"""

from typing import Dict, Optional
from urllib.parse import quote

from ai.http_session_pool import get_http_session

_HTTP_TIMEOUT = 8
_WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
_WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"


def _fallback_image_search(query: str) -> Dict:
    """Google Custom Search image fallback - only reached when Wikipedia
    couldn't produce a real photo. Returns the same success/failure shape
    as _show_image() so the caller can use it as a drop-in second try."""
    try:
        from search.image_search import get_image_search

        results = get_image_search().search(query, num=1)
    except Exception as e:
        return {"success": False, "error": f"Fallback image search unavailable: {e}"}

    if not results:
        return {
            "success": False,
            "error": f"No verified photo found for '{query}' on Wikipedia or web image search.",
        }

    top = results[0]
    return {
        "success": True,
        "query": query,
        "title": top.get("title") or query,
        "image_url": top.get("image_url"),
        "description": "",
        "source": "Google Image Search",
        "source_url": top.get("context_url", ""),
    }


def _resolve_wikipedia_title(query: str) -> Optional[str]:
    """The user's phrasing ('khesari lal yadav', 'the eiffel tower') often
    doesn't match the exact Wikipedia article title - use Wikipedia's own
    opensearch endpoint to resolve it to the real title first."""
    try:
        resp = get_http_session().get(
            _WIKI_SEARCH_URL,
            params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        titles = data[1] if len(data) > 1 else []
        return titles[0] if titles else None
    except Exception:
        return None


def _emit_image_ready(image_url: str, title: str, description: str, source_url: str) -> None:
    # Push it to the live dashboard - see ui/web_dashboard/app.py's
    # _wire_events() for the subscriber that relays this over SSE.
    try:
        from core.events import get_event_bus

        get_event_bus().emit(
            "image_ready",
            url=image_url,
            title=title,
            description=description,
            source_url=source_url,
        )
    except Exception:
        # Dashboard not running / event bus unavailable - the tool call
        # itself still succeeded (the model still gets the real image
        # URL back), only the live on-screen display is skipped.
        from core.error_trace import log_swallowed as _lsw

        _lsw("ai.image_display_tools._emit_image_ready")


def _show_image(args: Dict) -> Dict:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"success": False, "error": "No subject given to find a photo of."}

    title = _resolve_wikipedia_title(query) or query
    wiki_failure_reason = None

    try:
        resp = get_http_session().get(
            _WIKI_SUMMARY_URL.format(quote(title.replace(" ", "_"))),
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code == 404:
            wiki_failure_reason = f"No Wikipedia article found for '{query}'."
            data = None
        else:
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        wiki_failure_reason = f"Wikipedia unavailable ({e})."
        data = None

    image_url = None
    if data is not None:
        thumb = data.get("thumbnail", {}) or {}
        image_url = thumb.get("source")
        if not image_url:
            wiki_failure_reason = f"Wikipedia article for '{query}' has no photo attached."

    if image_url:
        page_title = data.get("title", title)
        description = data.get("description") or data.get("extract", "")[:200]
        page_url = (data.get("content_urls", {}) or {}).get("desktop", {}).get("page", "")
        _emit_image_ready(image_url, page_title, description, page_url)
        return {
            "success": True,
            "query": query,
            "title": page_title,
            "image_url": image_url,
            "description": description,
            "source": "Wikipedia",
            "source_url": page_url,
            "note": "Shown live on the web dashboard if it's open.",
        }

    # Wikipedia had nothing usable - try the fallback image search
    # (real search-engine photo, still never generated/guessed) before
    # giving up.
    fallback = _fallback_image_search(query)
    if fallback.get("success"):
        _emit_image_ready(
            fallback["image_url"],
            fallback["title"],
            fallback.get("description", ""),
            fallback.get("source_url", ""),
        )
        fallback["note"] = "Shown live on the web dashboard if it's open."
        fallback["fallback_reason"] = wiki_failure_reason
        return fallback

    return {
        "success": False,
        "error": f"{wiki_failure_reason} {fallback.get('error', '')} "
        f"Not showing an image since none could be verified as real.".strip(),
    }


IMAGE_DISPLAY_DIRECT_HANDLERS = {
    "show_image": _show_image,
}


IMAGE_DISPLAY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show_image",
            "description": (
                "Show a real, verified photo of a person, place, or thing on the live "
                "web dashboard (e.g. 'show me a photo of the Eiffel Tower', 'show me "
                "Khesari Lal Yadav'). Uses Wikipedia's real article photo first, falling "
                "back to a real web image search - never generates or guesses an image."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The subject to find a real photo of.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]
