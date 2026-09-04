"""
TTS Preparer (Phase 19.9 - Smart Answer Reader)
==================================================
Last step before a piece of text reaches an actual speech engine:
strips markdown syntax a TTS engine would otherwise read aloud
literally (asterisks, backticks, header hashes, link brackets),
expands symbols and abbreviations into words (%, &, @, e.g., i.e.,
etc.), and turns list markers into spoken transitions ("- " / "1. "
-> "First, ", "Next, ", ...) so a formatted list doesn't come out as
a wall of run-on words.

This is purely a text-cleanup pass, same spirit as tone-neutral
string utilities elsewhere in the project - it has no opinion on
*which* text should be spoken (adaptive_formatter.py's job) or how
long it should be (summarizer.py's / length_detector.py's job). It
runs last, after adaptive_formatter.py has already picked primary_text.

Stateless: no persistence, same as relation_mapper.py in Phase 19.7.
"""

import re
import threading
from typing import Dict, List, Optional

_instance: Optional["TTSPreparer"] = None
_instance_lock = threading.Lock()

_CODE_FENCE_RE = re.compile(r"```(?:\w+)?\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_HEADER_RE = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_BOLD_ITALIC_RE = re.compile(r"(\*{1,3}|_{1,3})(\S.*?\S|\S)\1")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BULLET_LINE_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_NUMBERED_LINE_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{2,}")

# order matters: longer/more-specific keys before the substrings they contain
_ABBREVIATIONS = [
    (r"\be\.g\.,?", "for example"),
    (r"\bi\.e\.,?", "that is"),
    (r"\betc\.", "and so on"),
    (r"\bvs\.", "versus"),
    (r"\bw/o\b", "without"),
    (r"\bw/\b", "with"),
    (r"\bapprox\.", "approximately"),
]
_SYMBOLS = [
    (r"%", " percent"),
    (r"&", " and "),
    (r"@", " at "),
    (r"\$(\d)", r"\1 dollars "),  # crude but keeps the number attached before "dollars"
]

_ORDINAL_WORDS = ["First", "Next", "Then", "After that", "Also", "Additionally", "Finally"]


class TTSPreparer:
    """final display/summary text -> {"speakable_text", "changes"}."""

    def prepare(self, text: str) -> Dict:
        text = text or ""
        changes: List[str] = []

        text = self._strip_code(text, changes)
        text = self._listify(text, changes)
        text = self._strip_markdown(text, changes)
        text = self._expand_abbreviations(text, changes)
        text = self._expand_symbols(text, changes)
        text = self._normalize_whitespace(text)

        return {"speakable_text": text.strip(), "changes": changes}

    @staticmethod
    def _strip_code(text: str, changes: List[str]) -> str:
        if _CODE_FENCE_RE.search(text):
            text = _CODE_FENCE_RE.sub(" a code snippet ", text)
            changes.append("replaced fenced code block(s) with 'a code snippet'")
        if _INLINE_CODE_RE.search(text):
            text = _INLINE_CODE_RE.sub(r"\1", text)
            changes.append("dropped inline-code backticks, kept the text")
        return text

    @staticmethod
    def _listify(text: str, changes: List[str]) -> str:
        """Turn bullet/numbered list lines into spoken transitions
        rather than reading the raw marker character aloud."""
        counter = {"i": 0}

        def _bullet_sub(_match):
            word = _ORDINAL_WORDS[counter["i"] % len(_ORDINAL_WORDS)]
            counter["i"] += 1
            return f"{word}, "

        if _BULLET_LINE_RE.search(text) or _NUMBERED_LINE_RE.search(text):
            text = _BULLET_LINE_RE.sub(_bullet_sub, text)
            text = _NUMBERED_LINE_RE.sub(_bullet_sub, text)
            changes.append("converted list markers into spoken transitions (First, Next, ...)")
        return text

    @staticmethod
    def _strip_markdown(text: str, changes: List[str]) -> str:
        if _LINK_RE.search(text):
            text = _LINK_RE.sub(r"\1", text)
            changes.append("replaced [text](url) links with just the link text")
        if _HEADER_RE.search(text):
            text = _HEADER_RE.sub("", text)
            changes.append("dropped markdown header hashes")
        if _BOLD_ITALIC_RE.search(text):
            text = _BOLD_ITALIC_RE.sub(r"\2", text)
            changes.append("dropped bold/italic asterisks or underscores")
        return text

    @staticmethod
    def _expand_abbreviations(text: str, changes: List[str]) -> str:
        for pattern, replacement in _ABBREVIATIONS:
            if re.search(pattern, text, re.IGNORECASE):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                changes.append(f"expanded abbreviation matching '{pattern}'")
        return text

    @staticmethod
    def _expand_symbols(text: str, changes: List[str]) -> str:
        for pattern, replacement in _SYMBOLS:
            if re.search(pattern, text):
                text = re.sub(pattern, replacement, text)
                changes.append(f"expanded symbol matching '{pattern}'")
        return text

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        text = _MULTI_NEWLINE_RE.sub(". ", text)
        text = text.replace("\n", ". ")
        text = _MULTI_SPACE_RE.sub(" ", text)
        text = re.sub(r"\s+([.,!?])", r"\1", text)
        text = re.sub(r"(\.\s*){2,}", ". ", text)
        return text


def get_tts_preparer() -> TTSPreparer:
    """Process-wide TTSPreparer singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = TTSPreparer()
    return _instance
