"""
Tool selector
=============
Picks the single best-matching tool from ai/tools_schema.py's TOOLS for
a user message, without needing a full LLM round trip. Distinct from
ai/planning.py (which sequences *multiple* tool calls for a multi-step
goal) - this is for "which one tool best matches what they just said",
e.g. to short-circuit straight to core/executor.py for an unambiguous
request, or to narrow the tool list passed to the model on a
constrained/offline turn.

Ranking is a lightweight keyword-overlap heuristic (name + description
word overlap with the message) so it's instant and works fully
offline; select_with_llm() is available as a fallback for ambiguous
cases where an LLM judgment call is worth the round trip.
"""

import os
import re
from typing import Dict, List

from ai.tools_schema import TOOLS

_WORD_RE = re.compile(r"[a-z0-9]+")

# Wake word + generic filler that shows up in almost every transcribed
# voice command ("Ultron, ...", "please", "sir") - left in, these count
# as a keyword "match" against any tool whose name/description happens
# to also contain "ultron" (e.g. get_api_usage, rag_answer), which both
# pollutes ranking with irrelevant candidates and (since score is a
# ratio, see below) can crowd out the tool that actually matches the
# request's real intent word. Stripped before scoring only - never
# touches the message actually sent to the model.
_FILLER_WORDS = {"ultron", "hey", "please", "sir", "kar", "karo", "do", "ok", "okay"}


def _words(text: str) -> set:
    return set(_WORD_RE.findall(text.lower())) - _FILLER_WORDS


# --- IDF-style word weighting ------------------------------------------
# BUG FIXED: plain keyword-overlap scoring treated every matched word as
# equally significant. In practice a word like "on" appears as a literal
# token in dozens of unrelated tool names/descriptions (on_battery_threshold,
# detect_objects_on_screen, toggle_narrator's "turn on/off"...), so a
# message like "wifi on kardo" scored 10+ completely unrelated tools at
# the exact same rank as the real wifi tool - just diluting the picked
# set with noise (and, in a tighter top_k, capable of pushing the real
# match out entirely). Hardcoding "on"/"off" into _FILLER_WORDS isn't
# safe either: those words carry real intent for tools that come in
# on/off *pairs* (enable_battery_saver vs disable_battery_saver) - if
# a message contains "off" and it's stripped, direction is lost.
#
# Fix: weight each word by how *rare* it is across the whole tool
# catalog (classic IDF). A word shared by 200 tools contributes almost
# nothing to the score; a word that appears in only 2-3 tools (e.g.
# "battery", "wifi") contributes heavily. This is computed once at
# import time directly from TOOLS, so it stays in sync automatically
# as tools are added/removed - no separate list to maintain.
def _build_doc_freq() -> Dict[str, int]:
    df: Dict[str, int] = {}
    for tool in TOOLS:
        fn = tool["function"]
        haystack = fn["name"].replace("_", " ") + " " + fn.get("description", "")
        for w in _words(haystack):
            df[w] = df.get(w, 0) + 1
    return df


_DOC_FREQ = _build_doc_freq()
_NUM_TOOLS = max(len(TOOLS), 1)


def _word_weight(word: str) -> float:
    """Rarer words (lower doc frequency) get a higher weight. A word
    that appears in every tool contributes ~0; a word unique to one
    tool contributes the most."""
    import math

    df = _DOC_FREQ.get(word, 1)
    return math.log((_NUM_TOOLS + 1) / (df + 1)) + 1.0


# --- API payload trimming --------------------------------------------
# ai/tools_schema.py's TOOLS has grown to 1567 entries (tools_schema.py
# itself + NEW_TOOLS + APPS_TOOLS + BROWSER_TOOLS + every *_control_tools
# module - sysconfig_*, procctl_*, filectl_*, netctl_*, secctl_*, uictl_*,
# etc - all merged at the bottom of that file) - several hundred KB of
# pure JSON if sent whole. ai/cloud_models/groq_client.py used to attach
# *all* of it to every single Groq call - the first call of a turn, and
# every follow-up call after a tool result comes back - even for
# something as small as "what time is it". That's the single biggest
# latency cost in the request pipeline. select_tools_for_api() reuses
# this module's keyword-overlap ranking (already used by select()/rank()
# above) to build a smaller subset instead, computed locally with no
# extra network call.
#
# BUG FIXED: MAX_TOOLS_PER_CALL used to be a hard 20, with the "no
# candidates at all" case as the only fallback to the full list. In
# practice almost every message scores *some* overlap with *something*
# (a single shared word like "open" or "check" is enough), so the full-list
# fallback almost never fired - meaning the entire sysconfig_*/procctl_*/
# filectl_*/netctl_*/secctl_*/uictl_* control layer (49-114 tools per
# category, ~500 tools total) was routinely invisible to the model even
# though it's fully registered and wired to real handlers in
# ai/tool_runtime.py. Two changes below fix that:
#   1. MAX_TOOLS_PER_CALL raised and now overridable via env var, so a
#      normal turn carries much more headroom before anything is dropped.
#   2. A *weak-match* fallback: if even the best-scoring candidate is a
#      poor match (score below _MIN_CONFIDENT_SCORE), the keyword ranking
#      isn't confident enough to be trusted to trim safely - send the full
#      list instead of gambling on a maybe-wrong top-N.
# Set ULTRON_FULL_TOOL_SCHEMA=1 to disable trimming entirely and always
# send the complete TOOLS list (safest re: capability, costs the most
# tokens/latency per call - useful while debugging "why didn't it call X").

_BY_NAME: Dict[str, Dict] = {t["function"]["name"]: t for t in TOOLS}

# Stay available every turn regardless of keyword match - either
# extremely common, or needed to make sense of a short/ambiguous
# follow-up ("cancel it").
_ALWAYS_INCLUDE = {
    "search_internet",
    "get_weather",
    "list_running_apps",
    "open_application",
    "cancel_shutdown",
}

# Overridable so this can be tuned per-deployment without a code change:
#   ULTRON_MAX_TOOLS_PER_CALL=80  -> more headroom, still trimmed
#   ULTRON_FULL_TOOL_SCHEMA=1     -> bypass trimming, always send all 1567
MAX_TOOLS_PER_CALL = int(os.environ.get("ULTRON_MAX_TOOLS_PER_CALL", "80"))

# Below this score, the keyword-overlap match is too weak to trust for
# trimming (e.g. only a filler-adjacent word overlapped) - send the full
# list rather than risk silently hiding the one tool the user actually
# needs.
_MIN_CONFIDENT_SCORE = 0.2


# BUG FIXED: the "not confident enough to trim" fallback used to return the
# ENTIRE 1567-tool list (~117K tokens, ~469KB of JSON) on every single
# model call for the turn. That's fine in *theory* ("never silently lose
# capability") but in practice it meant any message with zero English
# keyword overlap - which is exactly what casual Hinglish/Hindi chat
# ("kay hal hai bhai", "kaisa hai tu") looks like to a keyword matcher -
# blew every model's context window (or the free-tier OpenRouter models'
# much smaller ones) the SAME way, on EVERY fallback model, on EVERY
# provider. That looked like "the AI isn't switching after one hits its
# limit" from the console, but every backend was actually failing the
# identical oversized-request error, not a real rate limit. Two-tier
# fallback instead of one flat "give up, send everything":
#   - zero overlap at all (true casual chat, no tool intent) -> send just
#     the small always-available set. Sending all 1567 tools wouldn't
#     have found a better match anyway, since NOTHING scored.
#   - some overlap but below the confidence bar (genuinely ambiguous
#     English-ish command) -> send a capped larger set (top N by weak
#     match), not the full catalog, so the safety net for real ambiguity
#     doesn't cost a request-size failure on every provider at once.
_FULL_FALLBACK_CAP = int(os.environ.get("ULTRON_WEAK_MATCH_FALLBACK_CAP", "250"))


def select_tools_for_api(message: str, max_tools: int = MAX_TOOLS_PER_CALL) -> List[Dict]:
    """Return the subset of TOOLS (full Groq tool-dict format, not just
    names) most relevant to `message`. See _FULL_FALLBACK_CAP note above
    for why this no longer dumps the complete 1567-tool list on every
    weak/ambiguous match - only the common, clearly-matched case gets the
    fastest trimmed payload, and even the "not confident" cases stay
    capped so no single turn can blow every provider's context window."""
    if os.environ.get("ULTRON_FULL_TOOL_SCHEMA", "").strip() in ("1", "true", "True"):
        return TOOLS

    def _with_always_include(tools_by_name: Dict[str, Dict]) -> List[Dict]:
        for name in _ALWAYS_INCLUDE:
            if name in _BY_NAME and name not in tools_by_name:
                tools_by_name[name] = _BY_NAME[name]
        return list(tools_by_name.values())

    ranked = ToolSelector().rank(message, top_k=max(max_tools, _FULL_FALLBACK_CAP))
    candidates = ranked["candidates"]

    if not candidates:
        # Zero keyword overlap with anything - casual chat/greeting most
        # likely. The full 1567-tool list wouldn't score any better here,
        # so there's no capability tradeoff in keeping this small.
        return _with_always_include({})

    if candidates[0]["score"] < _MIN_CONFIDENT_SCORE:
        # Weak/ambiguous match - use the capped weak-match set instead of
        # the entire catalog, so this stays within every provider's
        # context budget while still surfacing the best partial matches.
        weak = candidates[:_FULL_FALLBACK_CAP]
        picked = {c["tool"]: _BY_NAME[c["tool"]] for c in weak if c["tool"] in _BY_NAME}
        return _with_always_include(picked)

    picked = {c["tool"]: _BY_NAME[c["tool"]] for c in candidates[:max_tools] if c["tool"] in _BY_NAME}
    return _with_always_include(picked)


class ToolSelector:
    """Rank/select the best-matching tool(s) for a user message."""

    def rank(self, message: str, top_k: int = 5) -> Dict:
        """Return the top_k tools ranked by keyword overlap with `message`."""
        message_words = _words(message)
        if not message_words:
            return {"message": message, "candidates": []}

        scored: List[Dict] = []
        for tool in TOOLS:
            fn = tool["function"]
            haystack = fn["name"].replace("_", " ") + " " + fn.get("description", "")
            tool_words = _words(haystack)
            overlap = message_words & tool_words
            if not overlap:
                continue
            # Score = IDF-weighted fraction of the USER'S words a tool
            # covers, not the other way around. The previous
            # len(overlap)/len(tool_words) formula punished tools with
            # long, well-written descriptions (more words in the
            # denominator = lower score even on an exact match) and
            # rewarded short/vague ones - e.g. a single "photo" match
            # used to rank show_image (a long, precise description)
            # below short unrelated tools that also happened to contain
            # "photo". Normalizing by the message's own word count
            # instead means a tool that matches most of what the user
            # actually said scores highest, regardless of how verbose
            # its own description is.
            #
            # Plain (unweighted) overlap/len(message_words) still let
            # a single common word (e.g. "on", shared by dozens of
            # tools) score exactly the same as a genuinely specific
            # match. Weighting each matched word by its rarity across
            # TOOLS (_word_weight) fixes that: matching a rare, on-topic
            # word like "wifi" or "battery" now scores far higher than
            # matching a generic word every tool happens to contain.
            matched_weight = sum(_word_weight(w) for w in overlap)
            total_weight = sum(_word_weight(w) for w in message_words)
            score = matched_weight / total_weight if total_weight else 0.0
            # Tie-break only (never the primary signal - see score above):
            # what fraction of the TOOL's own words got matched. Two
            # tools that both match on a single shared word (e.g.
            # "battery") tie on `score`, but a short/specific tool like
            # get_battery_status ("get battery status") has that one
            # word covering a much bigger share of its own description
            # than a verbose one like monctl_battery_generate_wear_report
            # does - so it's the more specific match and should sort
            # first. This mirrors real ambiguity too: two genuinely
            # opposite tools (enable_battery_saver vs
            # disable_battery_saver) are equally specific and will
            # legitimately stay tied - that's a case for
            # select_with_llm(), not something a keyword heuristic
            # should guess at.
            coverage = len(overlap) / max(len(tool_words), 1)
            scored.append(
                {
                    "tool": fn["name"],
                    "score": round(score, 4),
                    "matched_words": sorted(overlap),
                    "_coverage": coverage,
                }
            )

        scored.sort(key=lambda r: (r["score"], r["_coverage"]), reverse=True)
        for r in scored:
            del r["_coverage"]
        return {"message": message, "candidates": scored[:top_k]}

    # BUG FIXED: this was 0.05 - low enough that almost any message
    # "succeeded" with a confident-looking result, even a full natural
    # sentence where the real intent word is just one of many. Example:
    # "mera laptop me battery kitna charge hai" (how much battery charge
    # is on my laptop) scored camera_detect_objects (a webcam tool) at
    # 0.27 - higher than the actual battery-status tool - purely because
    # "laptop" happens to appear as a COCO object-class name in that
    # tool's unrelated description. core/orchestrator.py's autonomous
    # run_goal() calls select() as its *last* fallback and executes
    # whatever it returns, with no LLM or human re-check for the tools
    # that aren't approval-gated - so a low-confidence coincidental
    # match here isn't just a bad suggestion, it's a wrong action taken
    # on the user's behalf.
    #
    # Short, simple commands ("check battery", "open chrome", "wifi on
    # kardo") reliably score 0.4+ because a couple of their words carry
    # nearly all the message's weight. Full natural-language sentences -
    # exactly how people actually phrase requests, especially in
    # Hinglish - spread that same weight across many more words, so the
    # one relevant keyword contributes a smaller share and the score
    # drops well below that, even for a *correct* match. Raising the bar
    # to 0.4 keeps the offline heuristic for the cases it's actually
    # reliable at (short/explicit commands) and makes it refuse
    # (return tool=None) on longer/ambiguous phrasing instead of
    # guessing - which pushes those cases to select_with_llm() (that
    # actually reads the whole command) or to being skipped as
    # non-actionable, both safer than a wrong silent execute.
    _MIN_SELECT_CONFIDENCE = 0.4

    def select(self, message: str) -> Dict:
        """Best single guess, or an empty result if nothing matches well
        enough to be worth acting on without confirmation."""
        ranked = self.rank(message, top_k=1)
        candidates = ranked["candidates"]
        if not candidates or candidates[0]["score"] < self._MIN_SELECT_CONFIDENCE:
            return {"message": message, "tool": None, "confidence": 0.0}
        best = candidates[0]
        return {"message": message, "tool": best["tool"], "confidence": best["score"]}

    def select_with_llm(self, message: str) -> Dict:
        """Fallback for ambiguous messages: ask the model to pick a tool
        name from the real tool list (still not executing anything)."""
        from ai.ai_router import get_router

        tool_names = [t["function"]["name"] for t in TOOLS]
        prompt = (
            "Pick the single best tool name for this request from the list below. "
            "Respond with ONLY the tool name, nothing else. If none fit, respond with 'none'.\n\n"
            f"Tools: {', '.join(tool_names)}\n\nRequest: {message}"
        )
        try:
            text = get_router().complete(prompt, temperature=0.0, max_tokens=20).strip()
            tool_name = text.strip("`\"' \n")
            if tool_name not in tool_names:
                return {"message": message, "tool": None, "raw": text}
            return {"message": message, "tool": tool_name}
        except Exception as e:
            return {"error": str(e)}
