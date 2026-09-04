"""
Proactive Intelligence (Phase 20.1)
=============================
ULTRON noticing things on its own and deciding whether, when, and how
to bring them up - as opposed to Phase 20's conversation_layer/, which
only handles turn-taking once an exchange is already happening. A
signal comes in (a reminder firing, a security alert, disk space
running low, a download finishing), gets classified, scored for
urgency, checked against the user's current do-not-disturb/quiet-hours/
context state, turned into an actual suggestion, and either spoken,
queued for the next natural opening, or just logged silently -
depending on how urgent it is and how okay it is to interrupt right
now:

    event_detector.py         - normalizes a raw signal into a
                                 recognized event, filters out unknown
                                 signal types and repeat detections.
                                 In-memory dedup cache only, no DB.
    urgency_calculator.py     - scores how urgent an event is.
                                 Stateless.
    user_disruption_guard.py  - is now an acceptable moment to
                                 interrupt (DND, quiet hours, in-call/
                                 fullscreen/idle context, per-category
                                 cooldown). Owns tables
                                 `guard_settings` and `interruption_log`.
    suggestion_generator.py   - what to actually say and what quick
                                 actions to offer. Stateless (in-memory
                                 phrasing rotation only).
    conversation_initiator.py - how to deliver it: interrupt now, wait
                                 for the next pause, or stay silent -
                                 checked against Phase 20's
                                 turn_manager.py. Owns table
                                 `initiations`.
    notification_manager.py   - the durable queue: pending, delivered,
                                 dismissed, snoozed. Owns table
                                 `notifications`.
    proactive_engine.py       - single entry point tying all of the
                                 above together; owns table
                                 `proactive_events`

Usage:
    from intelligence.proactive_intelligence import get_proactive_engine
    engine = get_proactive_engine()

    result = engine.process_signal(
        {"signal_type": "battery_low", "payload": {"title": "Battery at 8%"}, "severity": "high"},
        context={"in_call": False, "fullscreen_active": False, "idle_seconds": 0},
        session_id=session_id,
    )
    # result["has_event"] -> False if the signal was unknown/a duplicate
    # result["initiation"]["mode"] -> "interrupt" / "next_pause" / "silent_notification" / "deferred"

    # a caller that owns the actual speaking/UI layer polls for what's
    # safe to say right now:
    deliverable = engine.get_next_deliverable(session_id)
    if deliverable:
        # ... speak/show deliverable["message"] ...
        engine.mark_notification_delivered(deliverable["id"])

    engine.set_do_not_disturb(True, minutes=30)
    engine.dismiss_notification(deliverable["id"])
    engine.snooze_notification(deliverable["id"], minutes=15)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through proactive_engine.py - e.g. call
urgency_calculator.py alone just to score an event, with no guard
check or delivery decision involved.

Purely additive - nothing in Phase 1-20 imports from here. The one
exception in the other direction: conversation_initiator.py reads
Phase 20's conversation_layer/turn_manager.py (read-only) to check
whether interrupting is currently safe.
"""

from intelligence.proactive_intelligence.event_detector import (
    EventDetector,
    get_event_detector,
    CATEGORY_REMINDER,
    CATEGORY_DEADLINE,
    CATEGORY_SYSTEM,
    CATEGORY_SECURITY,
    CATEGORY_COMMUNICATION,
    CATEGORY_TASK_COMPLETE,
    CATEGORY_ROUTINE,
)
from intelligence.proactive_intelligence.urgency_calculator import (
    UrgencyCalculator,
    get_urgency_calculator,
    URGENCY_LOW,
    URGENCY_MEDIUM,
    URGENCY_HIGH,
    URGENCY_CRITICAL,
)
from intelligence.proactive_intelligence.user_disruption_guard import (
    UserDisruptionGuard,
    get_user_disruption_guard,
    DECISION_ALLOW,
    DECISION_DEFER,
    DECISION_SUPPRESS,
)
from intelligence.proactive_intelligence.suggestion_generator import SuggestionGenerator, get_suggestion_generator
from intelligence.proactive_intelligence.conversation_initiator import (
    ConversationInitiator,
    get_conversation_initiator,
    MODE_INTERRUPT,
    MODE_NEXT_PAUSE,
    MODE_SILENT,
    MODE_DEFERRED,
)
from intelligence.proactive_intelligence.notification_manager import (
    NotificationManager,
    get_notification_manager,
    STATUS_PENDING,
    STATUS_DELIVERED,
    STATUS_DISMISSED,
    STATUS_SNOOZED,
    STATUS_EXPIRED,
)
from intelligence.proactive_intelligence.proactive_engine import ProactiveEngine, get_proactive_engine

__all__ = [
    "ProactiveEngine",
    "get_proactive_engine",
    "EventDetector",
    "get_event_detector",
    "CATEGORY_REMINDER",
    "CATEGORY_DEADLINE",
    "CATEGORY_SYSTEM",
    "CATEGORY_SECURITY",
    "CATEGORY_COMMUNICATION",
    "CATEGORY_TASK_COMPLETE",
    "CATEGORY_ROUTINE",
    "UrgencyCalculator",
    "get_urgency_calculator",
    "URGENCY_LOW",
    "URGENCY_MEDIUM",
    "URGENCY_HIGH",
    "URGENCY_CRITICAL",
    "UserDisruptionGuard",
    "get_user_disruption_guard",
    "DECISION_ALLOW",
    "DECISION_DEFER",
    "DECISION_SUPPRESS",
    "SuggestionGenerator",
    "get_suggestion_generator",
    "ConversationInitiator",
    "get_conversation_initiator",
    "MODE_INTERRUPT",
    "MODE_NEXT_PAUSE",
    "MODE_SILENT",
    "MODE_DEFERRED",
    "NotificationManager",
    "get_notification_manager",
    "STATUS_PENDING",
    "STATUS_DELIVERED",
    "STATUS_DISMISSED",
    "STATUS_SNOOZED",
    "STATUS_EXPIRED",
]
