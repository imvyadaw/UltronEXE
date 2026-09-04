"""Offline knowledge base tool
=============================
search_offline_knowledge (knowledge_base/offline_wiki/) - a local, no-internet
Wikipedia-summary index. This is a deliberate LAST RESORT, not a normal
search tool: search_internet already tries live Wikipedia -> Google ->
DuckDuckGo first and all three are more current. Only reach for this one
when the user has explicitly said they're offline, or a prior
search_internet call in the same conversation already failed.
"""

from ai.tools_schema import _tool

OFFLINE_KB_TOOLS = [
    _tool(
        "search_offline_knowledge",
        "Search a small LOCAL, offline Wikipedia-summary index for general "
        'factual/definitional knowledge ("what is X", "who is X"). Only use '
        "this when there is no internet available or search_internet has "
        "already failed in this conversation - it is a static, possibly "
        "outdated fallback, never the first choice over a live search. "
        "Not useful for current events, prices, or anything time-sensitive.",
        {"query": {"type": "string", "description": "What to look up"}},
        ["query"],
    ),
]
