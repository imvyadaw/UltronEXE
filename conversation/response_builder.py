"""
Response builder
=================
Final assembly step for a proactive/scenario message: picks a line via
proactive/personality/tone_manager.py, records it on
conversation/context_engine.py so a later reply can be linked back to
it, and returns the shape proactive/engine.py needs to actually deliver
it (ui.notifications.notify() + optionally speak it). Also builds the
short acknowledgement replies used after conversation/intent_analyzer.py
classifies what the user meant (SNOOZE/DISMISS/ACT/ACKNOWLEDGE), so
those don't need their own ad-hoc string formatting scattered across
scenarios/.
"""

from typing import Dict, Optional

from proactive.personality.tone_manager import get_tone_manager, Tone
from conversation.context_engine import get_context_engine
from conversation.intent_analyzer import Intent, IntentResult


class ResponseBuilder:
    """Turns a (category, kwargs) proactive event into delivery-ready text,
    and turns a classified user reply into a short follow-up line."""

    def __init__(self):
        self._tone_manager = get_tone_manager()
        self._context = get_context_engine()

    def build_alert(self, category: str, tone: Optional[Tone] = None, **kwargs) -> Dict:
        """Returns {"text", "tone", "level", "category"} and records the turn
        so a follow-up reply can be linked back to it via context_engine."""
        phrase = self._tone_manager.get_phrase(category, tone=tone, **kwargs)
        self._context.record_turn(category, phrase["text"], kwargs)
        return phrase

    def build_reply_ack(self, result: IntentResult) -> str:
        """Short, natural follow-up after classifying the user's reply to an
        alert - not a fresh alert, so this bypasses tone_manager's phrase
        bank and just returns a plain line."""
        if result.intent == Intent.ACKNOWLEDGE:
            return "Noted, Sir."
        if result.intent == Intent.DISMISS:
            return "Understood - I'll leave it be."
        if result.intent == Intent.SNOOZE:
            minutes = result.snooze_minutes or 10
            return f"Will do, Sir - I'll remind you again in {minutes} minutes."
        if result.intent == Intent.ACT:
            return "Right away, Sir."
        return "Sorry, Sir - could you say that again?"


_builder: Optional[ResponseBuilder] = None


def get_response_builder() -> ResponseBuilder:
    global _builder
    if _builder is None:
        _builder = ResponseBuilder()
    return _builder
