"""
Urgency Calculator (Phase 20.1 - Proactive Intelligence)
==================================================
Scores how urgent a detected event is, so user_disruption_guard.py
has something to weigh against quiet hours/DND and
conversation_initiator.py knows whether something is worth cutting
in for versus queuing for the next natural opening.

Deliberately simple/heuristic, same spirit as emotional_tone.py in
Phase 20: a base weight per category, then additive/subtractive
nudges from a handful of concrete signals - a caller-supplied
severity_hint, how close a deadline in the payload is, and a short
urgent-keyword scan over the title/description. Nothing here is a
hard cutoff; urgency_score is a continuous [0, 1] value and
urgency_level is just that score bucketed, so a caller that wants its
own cutoff can use the raw score directly.

Stateless: no persistence. This module only scores a single event
given to it - it never looks at event history itself (that's for
whatever's tracking recurrence upstream, e.g. event_detector.py's
dedup cache) and never decides what to do with the score
(user_disruption_guard.py's and conversation_initiator.py's jobs).
"""

import re
import threading
import time
from typing import Dict, List, Optional

_instance: Optional["UrgencyCalculator"] = None
_instance_lock = threading.Lock()

URGENCY_LOW = "low"
URGENCY_MEDIUM = "medium"
URGENCY_HIGH = "high"
URGENCY_CRITICAL = "critical"

# ordered high -> low; first threshold the score clears wins
_LEVEL_THRESHOLDS = (
    (0.85, URGENCY_CRITICAL),
    (0.60, URGENCY_HIGH),
    (0.35, URGENCY_MEDIUM),
    (0.00, URGENCY_LOW),
)

# base urgency before any event-specific adjustment - security issues
# and hard deadlines start highest, a routine nudge starts lowest
_CATEGORY_BASE_URGENCY = {
    "security": 0.70,
    "deadline": 0.55,
    "system": 0.45,
    "reminder": 0.40,
    "communication": 0.35,
    "task_complete": 0.25,
    "routine": 0.15,
}

_SEVERITY_HINT_ADJUSTMENT = {
    "critical": 0.30,
    "high": 0.20,
    "medium": 0.05,
    "low": -0.10,
}

# deadline proximity brackets: (max seconds remaining, adjustment).
# checked in order, first bracket the remaining time fits wins
_DEADLINE_BRACKETS = (
    (0, 0.35),  # already overdue
    (300, 0.30),  # <= 5 minutes
    (1800, 0.20),  # <= 30 minutes
    (7200, 0.10),  # <= 2 hours
    (86400, 0.0),  # <= 1 day
)
_DEADLINE_FAR_OUT_ADJUSTMENT = -0.10  # more than a day away - can wait

_URGENT_KEYWORDS = {
    "asap",
    "urgent",
    "immediately",
    "right now",
    "critical",
    "emergency",
    "as soon as possible",
    "overdue",
    "expiring",
}

_ALL_CAPS_WORD_RE = re.compile(r"\b[A-Z]{3,}\b")


class UrgencyCalculator:
    """(event, context) -> {"urgency_score", "urgency_level", "reasons"}."""

    def calculate(self, event: Dict, context: Optional[Dict] = None) -> Dict:
        context = context or {}
        reasons: List[str] = []

        category = event.get("category")
        score = _CATEGORY_BASE_URGENCY.get(category, 0.30)
        reasons.append(f"base urgency for category '{category}' is {score:.2f}")

        severity_hint = event.get("severity_hint")
        if severity_hint in _SEVERITY_HINT_ADJUSTMENT:
            adjustment = _SEVERITY_HINT_ADJUSTMENT[severity_hint]
            score += adjustment
            reasons.append(f"severity_hint '{severity_hint}' adjusts score by {adjustment:+.2f}")

        payload = event.get("payload") or {}
        due_at = payload.get("due_at") or payload.get("expires_at")
        if isinstance(due_at, (int, float)):
            remaining = due_at - time.time()
            adjustment = self._deadline_adjustment(remaining)
            score += adjustment
            reasons.append(f"deadline is {remaining:.0f}s away, adjusts score by {adjustment:+.2f}")

        text = f"{event.get('title', '')} {event.get('description', '')}".lower()
        matched_keywords = [kw for kw in _URGENT_KEYWORDS if kw in text]
        if matched_keywords:
            score += 0.15
            reasons.append(f"matched urgent keyword(s): {', '.join(matched_keywords)}")

        if _ALL_CAPS_WORD_RE.search(event.get("title", "") + " " + event.get("description", "")):
            score += 0.05
            reasons.append("title/description contains an ALL-CAPS word")

        if context.get("recent_occurrences", 0) and context["recent_occurrences"] >= 3:
            score += 0.10
            reasons.append(f"this has recurred {context['recent_occurrences']} times recently - escalating")

        score = max(0.0, min(1.0, score))
        level = self._level_for_score(score)
        reasons.append(f"final score {score:.2f} maps to urgency level '{level}'")

        return {"urgency_score": round(score, 3), "urgency_level": level, "reasons": reasons}

    @staticmethod
    def _deadline_adjustment(remaining_seconds: float) -> float:
        for max_seconds, adjustment in _DEADLINE_BRACKETS:
            if remaining_seconds <= max_seconds:
                return adjustment
        return _DEADLINE_FAR_OUT_ADJUSTMENT

    @staticmethod
    def _level_for_score(score: float) -> str:
        for threshold, level in _LEVEL_THRESHOLDS:
            if score >= threshold:
                return level
        return URGENCY_LOW


def get_urgency_calculator() -> UrgencyCalculator:
    """Process-wide UrgencyCalculator singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = UrgencyCalculator()
    return _instance
