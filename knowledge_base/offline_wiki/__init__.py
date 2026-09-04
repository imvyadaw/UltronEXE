"""knowledge_base/offline_wiki package
=====================================
Local, no-internet-required fallback knowledge base (Wikipedia intro
paragraphs, Tier A / "compact" scope - see ingest.py's module docstring
for what that means and how to build it).

This is deliberately last-resort: skills/internet/web_tools.py's
search_internet() already tries live Wikipedia -> Google Custom Search ->
DuckDuckGo Lite first, all of which are more current than anything baked
into a static local index. get_offline_kb().search() is only meant to be
reached when every one of those has failed (e.g. genuinely no internet
connection) - see the fallback wiring in web_tools.py.

Off by default: even with the index built, search_offline_knowledge (the
AI-facing tool) and the internal fallback path both check
ULTRON_OFFLINE_KB_ENABLED before doing anything, same convention as
ULTRON_DEVICES_ENABLED / ULTRON_AUTONOMOUS_WEB_ENABLED in
ai/phase30_gated_tools.py - a multi-hundred-MB local index isn't
something every install should silently carry.
"""

import os
from typing import Dict

from core.logger import get_logger

logger = get_logger("offline_wiki")

_kb = None


def offline_kb_enabled() -> bool:
    return os.getenv("ULTRON_OFFLINE_KB_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def get_offline_kb():
    """Lazy singleton, same pattern as memory/vector_db.get_vector_store().
    Returns None (not a raised exception) if hnswlib isn't installed or the
    index hasn't been built yet - callers check for None rather than
    wrapping every call in try/except."""
    global _kb
    if _kb is not None:
        return _kb

    try:
        from knowledge_base.offline_wiki.hnsw_store import OfflineWikiStore, HAS_HNSWLIB

        if not HAS_HNSWLIB:
            logger.info("Offline KB: hnswlib not installed, offline fallback unavailable.")
            return None
        _kb = OfflineWikiStore()
        return _kb
    except Exception as e:
        logger.warning("Offline KB failed to initialize: %s", e)
        return None


def search_offline(query: str, top_k: int = 3) -> Dict:
    """Safe entry point - never raises, always returns a Dict. Returns
    {"success": False, "error": ...} if the KB is disabled, not installed,
    or empty, so callers (the AI tool handler and web_tools.py's fallback)
    can just check "success" without needing to know why it failed."""
    if not offline_kb_enabled():
        return {"success": False, "error": "Offline KB disabled. Set ULTRON_OFFLINE_KB_ENABLED=true in .env."}

    kb = get_offline_kb()
    if kb is None:
        return {"success": False, "error": "Offline KB not available (hnswlib not installed or index not built)."}

    result = kb.similarity_search(query, top_k=top_k)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    if not result.get("results"):
        return {"success": False, "error": "No offline results found for this query."}

    return {
        "success": True,
        "source": "offline_wikipedia",
        "results": [{"title": r["title"], "url": r["url"], "description": r["text"]} for r in result["results"]],
        "count": len(result["results"]),
    }
