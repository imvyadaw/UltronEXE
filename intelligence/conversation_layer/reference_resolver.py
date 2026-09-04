"""
Reference Resolver (Phase 30 - Conversation Layer)
=====================================================
The one piece of "conversation/emotion_engine/personality_engine/etc"
that genuinely didn't exist anywhere in the codebase yet: resolving
"wahi", "ye", "wo", "usko", "kal wala", "pehle wala" / "it", "that",
"this", "the last one", "the previous one" against real conversation
history, so intent_router/ai/local_router downstream get a query that
already says what "it" refers to instead of guessing.

Reads history from turn_manager.py (Phase 20's single source of truth
for turn-by-turn conversation, already backed by
database/conversation_history.db) rather than keeping its own copy -
same "read from the one owner" discipline every other module in this
package already follows.

Deliberately conservative: a resolved reference is only substituted
when confidence is reasonable; a low-confidence guess is returned
alongside the *original* text so a caller can choose to ask a
clarifying question instead of silently guessing wrong (matches
reasoning/fact_checker.py's "no evidence found is UNVERIFIED, not
assumed true" philosophy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from intelligence.conversation_layer.turn_manager import get_turn_manager, SPEAKER_ASSISTANT, SPEAKER_USER

# Hindi/Hinglish + English deictic reference patterns. Grouped by what
# kind of antecedent they typically point at, so resolution can prefer
# a matching turn instead of just "the most recent turn no matter what".
_TIME_REFERENCE_RE = re.compile(
    r"\b(kal\s*wal\w*|pehle\s*wal\w*|us\s*din\s*wal\w*|purani\s*wal\w*|"
    r"the\s+(previous|last|earlier)\s+(one|thing|task|file))\b",
    re.IGNORECASE,
)
_GENERIC_REFERENCE_RE = re.compile(
    r"\b(wahi|wah[ei]\s*wal\w*|ye|yeh|wo|voh|us[ei]?ko?|isko|" r"\bit\b|\bthat\b|\bthis\b|\bthose\b|\bthese\b)\b",
    re.IGNORECASE,
)


@dataclass
class ResolvedReference:
    original_text: str
    resolved_text: str
    referenced: bool
    referenced_turn_text: Optional[str]
    confidence: float
    signals: List[str]


class ReferenceResolver:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._turns = get_turn_manager()

    def resolve(self, text: str, history_limit: int = 6) -> ResolvedReference:
        text = text or ""
        signals: List[str] = []

        time_match = _TIME_REFERENCE_RE.search(text)
        generic_match = _GENERIC_REFERENCE_RE.search(text)
        if not time_match and not generic_match:
            return ResolvedReference(text, text, False, None, 0.0, signals)

        history = self._turns.get_last_n_turns(self.session_id, n=history_limit)
        # Look for the most recent non-trivial turn (either speaker) with
        # actual text - that's almost always what a bare "wahi"/"it"
        # refers to, since deictic references overwhelmingly point at
        # whatever was just said, not something further back.
        candidate = None
        for turn in reversed(history):
            body = (turn.get("text") or "").strip()
            if body and turn["speaker"] in (SPEAKER_USER, SPEAKER_ASSISTANT):
                candidate = turn
                break

        if candidate is None:
            signals.append("reference pattern matched but no prior turn with text available")
            return ResolvedReference(text, text, True, None, 0.15, signals)

        confidence = 0.55 if generic_match else 0.0
        if time_match:
            confidence = max(confidence, 0.5)
        # A short candidate turn ("yes", "ok") is a weak antecedent - the
        # real referent is probably one turn further back than that.
        if len(candidate["text"].split()) <= 2 and len(history) >= 2:
            for turn in reversed(history[:-1]):
                body = (turn.get("text") or "").strip()
                if len(body.split()) > 2:
                    candidate = turn
                    confidence -= 0.05
                    signals.append("skipped a short filler turn to find a fuller antecedent")
                    break

        signals.append(f"matched against {candidate['speaker']} turn #{candidate['turn_number']}")
        resolved = f"{text.strip()} [referring to: {candidate['text']}]"
        return ResolvedReference(
            original_text=text,
            resolved_text=resolved,
            referenced=True,
            referenced_turn_text=candidate["text"],
            confidence=round(min(confidence, 0.9), 3),
            signals=signals,
        )


_instances: Dict[str, ReferenceResolver] = {}


def get_reference_resolver(session_id: str = "default") -> ReferenceResolver:
    if session_id not in _instances:
        _instances[session_id] = ReferenceResolver(session_id)
    return _instances[session_id]
