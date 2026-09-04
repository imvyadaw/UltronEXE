"""
Entity Extractor (Phase 19.7 - Knowledge Graph)
==================================================
Pulls candidate entities - people, projects, organizations, tools,
places, dates - out of raw text (a conversation turn, a note, an
action's params, anything) so knowledge_graph_engine.py has something
to turn into kg_nodes. Deliberately simple/heuristic, same spirit as
Phase 19.6's regex-based workflow detection: capitalized-word runs
are candidate proper nouns, a handful of keyword/pattern lists narrow
those down to a type, and an explicit `hints` dict always wins when
the caller already knows what something is (e.g. "Vishal" is always
a person here, no need to guess every time).

This module only extracts - it never decides how two entities relate
(relation_mapper.py) or persists anything (graph_store.py).
"""

import re
import threading
from typing import Dict, List, Optional

_instance: Optional["EntityExtractor"] = None
_instance_lock = threading.Lock()

# words that title-case matching would otherwise pick up but aren't entities
_STOPWORDS = {
    "the",
    "a",
    "an",
    "i",
    "im",
    "hi",
    "hey",
    "ok",
    "okay",
    "yes",
    "no",
    "today",
    "tomorrow",
    "yesterday",
    "now",
    "please",
    "thanks",
    "hello",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

_PROJECT_KEYWORDS = {"ultron"}
_PROJECT_PATTERN = re.compile(r"\bphase\s+\d+(?:\.\d+)?\b", re.IGNORECASE)

_ORG_SUFFIXES = ("inc", "llc", "ltd", "corp", "corporation", "co", "labs", "technologies", "systems")

_TOOL_KEYWORDS = {
    "python",
    "groq",
    "sqlite",
    "windows",
    "psutil",
    "pycaw",
    "screen_brightness_control",
    "vscode",
    "git",
    "github",
}

_DATE_PATTERN = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)\b",
    re.IGNORECASE,
)

# a capitalized word, or a run of them (e.g. "New York", "Vishal Kumar")
_PROPER_NOUN_PATTERN = re.compile(r"\b[A-Z][a-zA-Z0-9_]*(?:\s+[A-Z][a-zA-Z0-9_]*)*\b")


class EntityExtractor:
    """text -> list of {"name", "display_name", "type", "start", "end"} candidates."""

    def extract(self, text: str, hints: Optional[Dict[str, str]] = None) -> List[Dict]:
        if not text or not text.strip():
            return []
        hints = {k.lower(): v for k, v in (hints or {}).items()}

        found: Dict[str, Dict] = {}  # normalized name -> best candidate, dedup within one call

        for match in _PROJECT_PATTERN.finditer(text):
            self._add(found, match.group(0), "phase", match.start(), match.end())

        for match in _DATE_PATTERN.finditer(text):
            self._add(found, match.group(0), "date", match.start(), match.end())

        for match in _PROPER_NOUN_PATTERN.finditer(text):
            raw = match.group(0)
            normalized = raw.lower().strip()
            if normalized in _STOPWORDS or len(normalized) < 2:
                continue
            if normalized in found:
                continue  # a phase/date pattern already claimed this span
            entity_type = self._classify(raw, normalized, text, match.start(), hints)
            if entity_type is None:
                continue
            self._add(found, raw, entity_type, match.start(), match.end())

        return list(found.values())

    def _classify(self, raw: str, normalized: str, text: str, position: int, hints: Dict[str, str]) -> Optional[str]:
        if normalized in hints:
            return hints[normalized]
        if normalized in _PROJECT_KEYWORDS:
            return "project"
        if normalized in _TOOL_KEYWORDS or normalized.lower() in _TOOL_KEYWORDS:
            return "tool"
        if any(normalized.endswith(f" {suffix}") or normalized == suffix for suffix in _ORG_SUFFIXES):
            return "org"
        if self._looks_like_person(raw, text, position):
            return "person"
        # a lone capitalized word with no other signal is weak evidence -
        # keep it, but as a generic "topic" rather than guessing wrong
        return "topic"

    @staticmethod
    def _looks_like_person(raw: str, text: str, position: int) -> bool:
        """Cheap heuristics only: a title right before it ("Mr Sharma"),
        or a multi-word capitalized run that isn't a known project/org/
        tool (e.g. "Vishal Kumar") reads as a person name more often
        than not."""
        preceding = text[max(0, position - 5) : position].strip().lower()
        if preceding in ("mr", "mr.", "mrs", "mrs.", "dr", "dr.", "ms", "ms."):
            return True
        return " " in raw and len(raw.split()) <= 3

    @staticmethod
    def _add(found: Dict[str, Dict], raw: str, entity_type: str, start: int, end: int) -> None:
        normalized = raw.lower().strip()
        if normalized not in found:
            found[normalized] = {
                "name": normalized,
                "display_name": raw.strip(),
                "type": entity_type,
                "start": start,
                "end": end,
            }


def get_entity_extractor() -> EntityExtractor:
    """Process-wide EntityExtractor singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EntityExtractor()
    return _instance
