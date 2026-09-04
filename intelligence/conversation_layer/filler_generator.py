"""
Filler Generator (Phase 20 - Conversation Layer)
==================================================
Picks a short, natural filler phrase for conversation_engine.py to
speak while the assistant needs a moment - waiting on a slow tool
call, thinking through a hard question, or just acknowledging it
heard the user before the real response is ready. Without this,
silence during a slow response reads as ULTRON having missed the
request entirely.

Phrases are grouped by reason (thinking / searching / processing /
acknowledgment) and, within a reason, lightly rotated so the same
process doesn't repeat the exact same filler back-to-back - a small
in-memory {reason: last_index} map, not persisted, since which filler
was said last is only relevant within a single running process and
resets harmlessly on restart. That's the only state this module
carries; it has no database table, unlike turn_manager.py/
response_timer.py.

Stateless with respect to persistence - no DB, same as
tts_preparer.py. This module only picks phrasing - it never decides
whether a filler is needed at all (conversation_engine.py's job,
usually driven by response_timer.py/tool latency).
"""

import random
import threading
from typing import Dict, List, Optional

_instance: Optional["FillerGenerator"] = None
_instance_lock = threading.Lock()

REASON_THINKING = "thinking"
REASON_SEARCHING = "searching"
REASON_PROCESSING = "processing"
REASON_ACKNOWLEDGMENT = "acknowledgment"

_PHRASES: Dict[str, List[str]] = {
    REASON_THINKING: [
        "Let me think about that for a second.",
        "Hmm, give me a moment.",
        "Let's see...",
        "Good question - thinking it through.",
    ],
    REASON_SEARCHING: [
        "Let me look that up.",
        "One moment while I check.",
        "Give me a second to find that.",
        "Checking on that now.",
    ],
    REASON_PROCESSING: [
        "Working on it.",
        "Just a second.",
        "On it - one moment.",
        "Almost there.",
    ],
    REASON_ACKNOWLEDGMENT: [
        "Got it.",
        "Sure thing.",
        "Okay.",
        "Understood.",
    ],
}

# tone-flavored variants a caller can ask for instead of the neutral
# defaults above - kept small since emotional_tone.py is the module
# with the real tone-classification logic, this just needs a couple
# of gentler options for when the user seemed frustrated/urgent
_TONE_OVERRIDES: Dict[str, Dict[str, List[str]]] = {
    "reassuring": {
        REASON_THINKING: ["No worries, let me work through that.", "I've got this - one moment."],
        REASON_PROCESSING: ["Almost done, hang tight.", "Still with you - just a moment more."],
    },
    "urgent": {
        REASON_THINKING: ["On it right now.", "Quick sec."],
        REASON_PROCESSING: ["Almost there.", "One second."],
    },
}


class FillerGenerator:
    """reason (+ optional tone) -> {"filler_text", "category"}."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_index: Dict[str, int] = {}

    def generate(self, reason: str = REASON_THINKING, tone: Optional[str] = None) -> Dict:
        reason = reason if reason in _PHRASES else REASON_THINKING
        pool = self._resolve_pool(reason, tone)

        with self._lock:
            last_index = self._last_index.get(reason, -1)
            if len(pool) == 1:
                index = 0
            else:
                index = random.randrange(len(pool))
                while index == last_index:
                    index = random.randrange(len(pool))
            self._last_index[reason] = index

        return {"filler_text": pool[index], "category": reason, "tone": tone}

    @staticmethod
    def _resolve_pool(reason: str, tone: Optional[str]) -> List[str]:
        if tone and tone in _TONE_OVERRIDES and reason in _TONE_OVERRIDES[tone]:
            return _TONE_OVERRIDES[tone][reason]
        return _PHRASES[reason]


def get_filler_generator() -> FillerGenerator:
    """Process-wide FillerGenerator singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = FillerGenerator()
    return _instance
