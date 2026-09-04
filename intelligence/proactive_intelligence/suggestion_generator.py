"""
Suggestion Generator (Phase 20.1 - Proactive Intelligence)
==================================================
Turns a detected event into the actual words ULTRON would say (or
show) about it, plus a short list of quick actions the user can take
without typing anything - "Snooze 10 min", "Open", "Dismiss", and so
on, tailored to the event's category.

Phrasing is template-based and grouped by category, same spirit as
filler_generator.py's phrase-bank-plus-rotation in Phase 20: a handful
of natural-sounding variants per category with a {title} placeholder,
lightly rotated so back-to-back notifications of the same category
don't all open with identical phrasing, plus an in-memory
{category: last_index} map - the only state this module carries, not
persisted, for the same reason filler_generator.py's isn't (which
phrasing was used last only matters within a single running process).

A critical-urgency event gets a short attention-getting prefix instead
of a different template set, so the underlying phrasing stays
consistent regardless of urgency and only the framing changes.

Stateless with respect to persistence - no DB. This module only picks
wording and suggested actions - it never decides whether to actually
say anything at all (user_disruption_guard.py's job) or how to
deliver it (conversation_initiator.py's job).
"""

import random
import threading
from typing import Dict, List, Optional

_instance: Optional["SuggestionGenerator"] = None
_instance_lock = threading.Lock()

URGENCY_CRITICAL = "critical"

_CRITICAL_PREFIX = "This needs your attention now - "

_TEMPLATES: Dict[str, List[str]] = {
    "reminder": [
        "Just a heads up - {title}.",
        "Don't forget: {title}.",
        "Reminder: {title}.",
    ],
    "deadline": [
        "Heads up, {title}.",
        "{title} - might be worth getting ahead of that.",
        "Flagging this one: {title}.",
    ],
    "system": [
        "Quick note: {title}.",
        "System notice - {title}.",
        "Worth knowing: {title}.",
    ],
    "security": [
        "I want to flag this - {title}.",
        "Security alert: {title}.",
        "Something you should look at: {title}.",
    ],
    "communication": [
        "You've got {title}.",
        "New: {title}.",
        "Heads up - {title}.",
    ],
    "task_complete": [
        "{title} - all done.",
        "Finished: {title}.",
        "That's wrapped up - {title}.",
    ],
    "routine": [
        "Since you're around - {title}.",
        "By the way, {title}.",
        "Quick one - {title}.",
    ],
}

_SUGGESTED_ACTIONS: Dict[str, List[str]] = {
    "reminder": ["Got it", "Snooze 10 min", "Dismiss"],
    "deadline": ["Open task", "Snooze", "Dismiss"],
    "system": ["Fix now", "Remind me later", "Dismiss"],
    "security": ["View details", "Dismiss"],
    "communication": ["Open", "Mark as read", "Dismiss"],
    "task_complete": ["Open result", "Dismiss"],
    "routine": ["Sure", "Not now"],
}

_DEFAULT_TEMPLATES = ["{title}."]
_DEFAULT_ACTIONS = ["Okay", "Dismiss"]


class SuggestionGenerator:
    """(event, urgency_level) -> {"message", "suggested_actions", "category"}."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_index: Dict[str, int] = {}

    def generate(self, event: Dict, urgency_level: str) -> Dict:
        category = event.get("category")
        title = event.get("title") or "something worth a look"
        description = event.get("description") or ""

        template = self._pick_template(category)
        message = template.format(title=title)
        if description:
            message = f"{message} ({description})"
        if urgency_level == URGENCY_CRITICAL:
            message = _CRITICAL_PREFIX + message

        actions = _SUGGESTED_ACTIONS.get(category, _DEFAULT_ACTIONS)
        return {"message": message, "suggested_actions": list(actions), "category": category}

    def _pick_template(self, category: Optional[str]) -> str:
        pool = _TEMPLATES.get(category, _DEFAULT_TEMPLATES)
        with self._lock:
            last_index = self._last_index.get(category, -1)
            if len(pool) == 1:
                index = 0
            else:
                index = random.randrange(len(pool))
                while index == last_index:
                    index = random.randrange(len(pool))
            self._last_index[category] = index
        return pool[index]


def get_suggestion_generator() -> SuggestionGenerator:
    """Process-wide SuggestionGenerator singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SuggestionGenerator()
    return _instance
