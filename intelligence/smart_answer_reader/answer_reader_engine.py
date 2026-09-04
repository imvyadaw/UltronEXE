"""
Answer Reader Engine (Phase 19.9 - Smart Answer Reader)
==================================================
Single entry point for the smart_answer_reader/ package: take a raw
answer ULTRON is about to present and turn it into what should
actually be shown on screen and/or spoken out loud. Ties together:

    length_detector.py   - how long/structured is this answer
    point_extractor.py   - what are its key points, if it's long enough to need them
    summarizer.py         - condensed one_liner/brief/detailed versions built from those points
    adaptive_formatter.py - which version (full text vs a summary) fits this output mode
    tts_preparer.py       - final cleanup pass on whatever's going to be spoken

Mirrors decision_gate.py's role in Phase 19.8 (a thin orchestrator
over otherwise-independent sub-modules that still work fine called
directly) and takes the entry-point role itself for the same reason:
every answer that needs reading-aware handling ends up here
regardless of which path led to it.

Unlike decision_gate.py, this module has no database - nothing here
is an outcome to record and learn from later, it's read-time
formatting of already-generated text. Every sub-module is stateless,
so the engine itself is too.

Purely additive - nothing in Phase 1-19.8 imports from here.
"""

import threading
from typing import Dict, Optional

from core.logger import get_logger
from intelligence.smart_answer_reader.length_detector import get_length_detector
from intelligence.smart_answer_reader.point_extractor import get_point_extractor
from intelligence.smart_answer_reader.summarizer import get_summarizer
from intelligence.smart_answer_reader.adaptive_formatter import (
    get_adaptive_formatter,
    MODE_VOICE,
    MODE_SCREEN,
)
from intelligence.smart_answer_reader.tts_preparer import get_tts_preparer

logger = get_logger("ultron.answer_reader_engine")

_instance: Optional["AnswerReaderEngine"] = None
_instance_lock = threading.Lock()


class AnswerReaderEngine:
    """Orchestrates length_detector / point_extractor / summarizer /
    adaptive_formatter / tts_preparer into read(), the one call most
    callers need."""

    def __init__(self):
        self._length = get_length_detector()
        self._points = get_point_extractor()
        self._summarizer = get_summarizer()
        self._formatter = get_adaptive_formatter()
        self._tts = get_tts_preparer()

    def read(self, text: str, mode: str = MODE_VOICE) -> Dict:
        """Full pipeline: classify -> extract points if warranted ->
        summarize at every style -> pick what this mode should
        actually present -> (voice only) clean it for a TTS engine.

        Returns everything a caller might want: the raw
        classification, the extracted points, the chosen
        primary_text/key_points from adaptive_formatter.py, and - for
        voice mode - speakable_text ready to hand to a speech engine.
        """
        text = text or ""
        mode = mode if mode in (MODE_VOICE, MODE_SCREEN) else MODE_VOICE

        length_info = self._length.detect(text)
        tier = length_info["length_tier"]

        points = []
        summaries_by_style = {}
        if length_info["recommendation"] == "summarize_first":
            points = self._points.extract_in_original_order(text, max_points=6)
            summaries_by_style = self._summarizer.summarize_all_styles(text)

        formatted = self._formatter.format_answer(
            text,
            length_info,
            mode=mode,
            summaries_by_style=summaries_by_style,
            points=points,
        )

        result = {
            "mode": mode,
            "length_tier": tier,
            "word_count": length_info["word_count"],
            "structure_flags": length_info["structure_flags"],
            "key_points": formatted["key_points"],
            "display_text": formatted["primary_text"] if mode == MODE_SCREEN else text.strip(),
            "offered_expansion": formatted["offered_expansion"],
            "expansion_hint": formatted["expansion_hint"],
        }

        if mode == MODE_VOICE:
            tts_result = self._tts.prepare(formatted["primary_text"])
            result["speakable_text"] = tts_result["speakable_text"]
            result["tts_changes"] = tts_result["changes"]

        logger.info(
            f"prepared answer for {mode}: tier={tier}, "
            f"words={length_info['word_count']}, expansion_offered={formatted['offered_expansion']}"
        )
        return result

    def read_full(self, text: str, mode: str = MODE_VOICE) -> Dict:
        """Bypass the summarize-first logic entirely and prepare the
        full answer for presentation - what a caller uses after the
        user takes up an expansion_hint offer from a prior read()."""
        text = text or ""
        mode = mode if mode in (MODE_VOICE, MODE_SCREEN) else MODE_VOICE
        length_info = self._length.detect(text)

        result = {
            "mode": mode,
            "length_tier": length_info["length_tier"],
            "word_count": length_info["word_count"],
            "structure_flags": length_info["structure_flags"],
            "key_points": [],
            "display_text": text.strip(),
            "offered_expansion": False,
            "expansion_hint": None,
        }
        if mode == MODE_VOICE:
            tts_result = self._tts.prepare(text)
            result["speakable_text"] = tts_result["speakable_text"]
            result["tts_changes"] = tts_result["changes"]
        return result


def get_answer_reader_engine() -> AnswerReaderEngine:
    """Process-wide AnswerReaderEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = AnswerReaderEngine()
    return _instance
