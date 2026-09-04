"""
Intent analyzer
===============
Lightweight, dependency-free classification of a user's reply to a
proactive alert - "what do they REALLY want": dismiss it, snooze it, act
on it, or ignore the alert and say something unrelated. Deliberately
keyword/heuristic-based rather than routing every two-word reply
("later", "yeah do it") through the full LLM (ai/ai_router.py) - that
round trip is overkill for a one-word acknowledgement and adds latency
right after Ultron just interrupted the user. Falls back to
UNRELATED/UNKNOWN for anything it isn't confident about, so the caller
(scenarios/*, proactive/engine.py) can hand ambiguous replies to the
normal chat path instead of guessing wrong.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from conversation.context_engine import get_context_engine, Turn


class Intent(str, Enum):
    ACKNOWLEDGE = "acknowledge"  # "ok", "got it", "thanks"
    DISMISS = "dismiss"  # "no", "ignore that", "not now"
    SNOOZE = "snooze"  # "remind me later", "in 10 minutes"
    ACT = "act"  # "yes do it", "go ahead", "show me"
    UNRELATED = "unrelated"  # doesn't look like a reply to the alert at all
    UNKNOWN = "unknown"  # couldn't classify confidently


@dataclass
class IntentResult:
    intent: Intent
    confidence: float  # 0..1, heuristic - not a calibrated probability
    related_turn: Optional[Turn]
    snooze_minutes: Optional[int] = None


_ACK_PATTERNS = [r"^ok(ay)?$", r"^got it$", r"^thanks?( you)?$", r"^cool$", r"^noted$", r"^alright$"]
_DISMISS_PATTERNS = [r"^no+$", r"not now", r"ignore (that|it)", r"never ?mind", r"^skip( it)?$", r"^dismiss$"]
_ACT_PATTERNS = [r"^yes", r"^yeah", r"^yep", r"^sure", r"go ahead", r"^do it$", r"show me", r"^please$"]
_SNOOZE_PATTERNS = [r"remind me (later|again)", r"^later$", r"in (\d+) ?min", r"snooze"]


def _matches_any(text: str, patterns: List[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _extract_snooze_minutes(text: str) -> Optional[int]:
    match = re.search(r"in (\d+) ?min", text)
    if match:
        return int(match.group(1))
    if "later" in text:
        return 10  # a sensible default when no explicit duration is given
    return None


class IntentAnalyzer:
    """Heuristic classifier for short replies to proactive alerts."""

    def __init__(self):
        self._context = get_context_engine()

    def analyze(self, message: str) -> IntentResult:
        text = (message or "").strip().lower()
        related_turn = self._context.last_unresolved_turn()

        if not text:
            return IntentResult(Intent.UNKNOWN, 0.0, related_turn)

        # Long messages (more than ~8 words) are much more likely a fresh
        # request than a one-line reaction to an alert.
        is_short = len(text.split()) <= 8

        if is_short and _matches_any(text, _SNOOZE_PATTERNS):
            return IntentResult(Intent.SNOOZE, 0.8, related_turn, snooze_minutes=_extract_snooze_minutes(text))
        if is_short and _matches_any(text, _DISMISS_PATTERNS):
            return IntentResult(Intent.DISMISS, 0.8, related_turn)
        if is_short and _matches_any(text, _ACT_PATTERNS) and related_turn is not None:
            return IntentResult(Intent.ACT, 0.7, related_turn)
        if is_short and _matches_any(text, _ACK_PATTERNS):
            return IntentResult(Intent.ACKNOWLEDGE, 0.75, related_turn)

        if related_turn is None:
            return IntentResult(Intent.UNRELATED, 0.5, None)

        return IntentResult(Intent.UNKNOWN, 0.3, related_turn)

    def apply(self, message: str) -> IntentResult:
        """analyze() + records the reply against the related turn (if any) so
        the context engine's history stays accurate. Most callers should
        use this rather than analyze() directly."""
        result = self.analyze(message)
        if result.related_turn is not None and result.intent != Intent.UNRELATED:
            resolved = result.intent != Intent.SNOOZE  # a snooze keeps the turn open
            self._context.record_reply(message, resolved=resolved)
        return result


_analyzer: Optional[IntentAnalyzer] = None


def get_intent_analyzer() -> IntentAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IntentAnalyzer()
    return _analyzer
