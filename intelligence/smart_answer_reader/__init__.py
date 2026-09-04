"""
Smart Answer Reader (Phase 19.9)
=============================
Takes any generated answer and decides what should actually be shown
on screen and/or spoken out loud, instead of always dumping the raw
text either way. Backed by no database - every sub-module is
stateless, read-time text processing only:

    length_detector.py   - classifies an answer as short/medium/long/
                            very_long from word count, and flags
                            structure (code, tables, lists, headers)
                            a raw TTS read would mangle
    point_extractor.py   - pulls out and ranks the sentences/list
                            items that best represent a long answer
    summarizer.py         - condenses those points into one_liner /
                            brief / detailed prose
    adaptive_formatter.py - picks what a given output mode (voice vs
                            screen) should actually present: full
                            text, or a summary plus an offer to hear/
                            see more
    tts_preparer.py       - final cleanup pass making chosen text
                            speakable (strips markdown, expands
                            symbols/abbreviations, turns list markers
                            into spoken transitions)
    answer_reader_engine.py - single entry point tying all of the
                            above together

Usage:
    from intelligence.smart_answer_reader import get_answer_reader_engine
    engine = get_answer_reader_engine()

    result = engine.read(long_answer_text, mode="voice")
    # result["speakable_text"]   -> ready for a TTS engine
    # result["offered_expansion"] -> True if it was summarized down
    # result["expansion_hint"]    -> e.g. "Want me to read the full answer?"

    # if the user says yes to the hint:
    full = engine.read_full(long_answer_text, mode="voice")

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through answer_reader_engine.py - e.g.
call length_detector.py alone just to check how long/structured an
answer is, with no summarizing or formatting involved.

Purely additive - nothing in Phase 1-19.8 imports from here.
"""

from intelligence.smart_answer_reader.length_detector import (
    LengthDetector,
    get_length_detector,
    TIER_SHORT,
    TIER_MEDIUM,
    TIER_LONG,
    TIER_VERY_LONG,
)
from intelligence.smart_answer_reader.point_extractor import PointExtractor, get_point_extractor
from intelligence.smart_answer_reader.summarizer import (
    Summarizer,
    get_summarizer,
    STYLE_ONE_LINER,
    STYLE_BRIEF,
    STYLE_DETAILED,
)
from intelligence.smart_answer_reader.adaptive_formatter import (
    AdaptiveFormatter,
    get_adaptive_formatter,
    MODE_VOICE,
    MODE_SCREEN,
)
from intelligence.smart_answer_reader.tts_preparer import TTSPreparer, get_tts_preparer
from intelligence.smart_answer_reader.answer_reader_engine import (
    AnswerReaderEngine,
    get_answer_reader_engine,
)

__all__ = [
    "AnswerReaderEngine",
    "get_answer_reader_engine",
    "MODE_VOICE",
    "MODE_SCREEN",
    "LengthDetector",
    "get_length_detector",
    "TIER_SHORT",
    "TIER_MEDIUM",
    "TIER_LONG",
    "TIER_VERY_LONG",
    "PointExtractor",
    "get_point_extractor",
    "Summarizer",
    "get_summarizer",
    "STYLE_ONE_LINER",
    "STYLE_BRIEF",
    "STYLE_DETAILED",
    "AdaptiveFormatter",
    "get_adaptive_formatter",
    "TTSPreparer",
    "get_tts_preparer",
]
