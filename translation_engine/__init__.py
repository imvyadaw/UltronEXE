"""
Translation engine
===================
Real-time Hinglish/multi-language translation. See
realtime_translator.py for the implementation - this package deliberately
has no local translation model bundled (none of this codebase's existing
dependencies include one); it goes through ai.ai_router.complete() the
same way ai/reasoning.py and ai/planning.py already do for single-shot,
no-tools, no-shared-history prompts.
"""

from translation_engine.realtime_translator import translate, detect_language, romanize_hindi

__all__ = ["translate", "detect_language", "romanize_hindi"]
