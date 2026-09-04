"""
Conversation Layer (Phase 20)
=============================
Turn-taking intelligence for live conversation: who's speaking right
now, whether incoming speech is a real interruption, whether a new
utterance continues the last topic, whether a pause means the user is
actually done talking, what tone the user sounds like they're in, and
what to say if the real response is going to take a moment. Backed by
a shared database at database/conversation_history.db:

    turn_manager.py       - source of truth for turn state/history;
                             start/end/interrupt a turn, owns table
                             `turns`
    barge_in_detector.py  - classifies incoming speech during the
                             assistant's turn as a real barge-in or
                             noise/echo, and what kind of interruption
                             it is. Stateless.
    continuity_tracker.py - scores whether a new turn continues the
                             prior topic or is a fresh start.
                             Stateless.
    response_timer.py     - adaptive endpointing: decides if a pause
                             means "respond now", and learns a
                             per-session wait threshold from reported
                             outcomes. Owns tables `pause_events` and
                             `timing_thresholds`.
    emotional_tone.py     - reads a rough tone off the user's text and
                             recommends a response tone. Stateless.
    filler_generator.py   - picks a natural filler phrase to speak
                             while a real response is still being
                             generated. In-memory rotation only, no DB.
    conversation_engine.py - single entry point tying all of the
                             above together; owns table
                             `conversation_events`
    reference_resolver.py - resolves "wahi"/"ye"/"kal wala"/"it"/"that"
                             against turn_manager's real history so
                             downstream routing gets what the reference
                             actually points at, not a bare pronoun.
                             Conservative: returns a confidence score
                             rather than guessing silently when unsure.

Usage:
    from intelligence.conversation_layer import get_conversation_engine
    engine = get_conversation_engine()

    engine.start_user_turn(session_id)
    decision = engine.process_user_utterance(session_id, text_so_far, pause_duration)
    # decision["should_respond"] -> bool
    # decision["recommended_response_tone"] -> e.g. "calm_reassuring"

    turn = engine.start_assistant_turn(session_id, expected_latency_seconds=2.5)
    # turn["filler_text"] -> speak this immediately if the real answer will take a moment
    engine.end_assistant_turn(session_id, turn["turn_id"], final_response_text)

    # mid-response, if speech comes in:
    barge = engine.handle_incoming_speech(session_id, incoming_signal)
    # barge["is_barge_in"] -> bool; barge["new_user_turn"] set if True

    # once the real outcome of a should_respond() call is known:
    engine.report_response_outcome(decision["pause_id"], was_correct=True)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through conversation_engine.py - e.g.
call barge_in_detector.py alone just to classify one interruption,
with no turn-taking or persistence beyond that check involved.

Purely additive - nothing in Phase 1-19.9 imports from here.
"""

from intelligence.conversation_layer.turn_manager import (
    TurnManager,
    get_turn_manager,
    SPEAKER_USER,
    SPEAKER_ASSISTANT,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_INTERRUPTED,
    TURN_TYPE_SPEECH,
    TURN_TYPE_TEXT,
)
from intelligence.conversation_layer.barge_in_detector import (
    BargeInDetector,
    get_barge_in_detector,
    BARGE_IN_TYPE_CORRECTION,
    BARGE_IN_TYPE_NEW_REQUEST,
    BARGE_IN_TYPE_GENERIC,
)
from intelligence.conversation_layer.continuity_tracker import ContinuityTracker, get_continuity_tracker
from intelligence.conversation_layer.response_timer import (
    ResponseTimer,
    get_response_timer,
    DECISION_RESPOND,
    DECISION_WAIT,
)
from intelligence.conversation_layer.filler_generator import (
    FillerGenerator,
    get_filler_generator,
    REASON_THINKING,
    REASON_SEARCHING,
    REASON_PROCESSING,
    REASON_ACKNOWLEDGMENT,
)
from intelligence.conversation_layer.emotional_tone import (
    EmotionalTone,
    get_emotional_tone,
    TONE_NEUTRAL,
    TONE_FRUSTRATED,
    TONE_URGENT,
    TONE_HAPPY,
    TONE_CONFUSED,
)
from intelligence.conversation_layer.conversation_engine import ConversationEngine, get_conversation_engine
from intelligence.conversation_layer.reference_resolver import (
    ReferenceResolver,
    get_reference_resolver,
    ResolvedReference,
)

__all__ = [
    "ConversationEngine",
    "get_conversation_engine",
    "ReferenceResolver",
    "get_reference_resolver",
    "ResolvedReference",
    "TurnManager",
    "get_turn_manager",
    "SPEAKER_USER",
    "SPEAKER_ASSISTANT",
    "STATUS_IN_PROGRESS",
    "STATUS_COMPLETED",
    "STATUS_INTERRUPTED",
    "TURN_TYPE_SPEECH",
    "TURN_TYPE_TEXT",
    "BargeInDetector",
    "get_barge_in_detector",
    "BARGE_IN_TYPE_CORRECTION",
    "BARGE_IN_TYPE_NEW_REQUEST",
    "BARGE_IN_TYPE_GENERIC",
    "ContinuityTracker",
    "get_continuity_tracker",
    "ResponseTimer",
    "get_response_timer",
    "DECISION_RESPOND",
    "DECISION_WAIT",
    "FillerGenerator",
    "get_filler_generator",
    "REASON_THINKING",
    "REASON_SEARCHING",
    "REASON_PROCESSING",
    "REASON_ACKNOWLEDGMENT",
    "EmotionalTone",
    "get_emotional_tone",
    "TONE_NEUTRAL",
    "TONE_FRUSTRATED",
    "TONE_URGENT",
    "TONE_HAPPY",
    "TONE_CONFUSED",
]
