"""
Intent Prediction (Phase 19.2)
=================================
Predicts what the user is currently trying to do, and what they're
likely to do next, built directly on top of Phase 19.1's
intelligence.world_state - backed by a single shared database at
database/intent_prediction.db:

    context_intent_mapper.py  - context (active app, time of day, task
                                 in flight) -> ranked candidate intents
    pattern_analyzer.py       - recurring intent-sequence mining, "what
                                 usually follows what"
    goal_predictor.py         - matches recent intents against
                                 caller-registered goals
    next_action_predictor.py  - intent-scoped action transition table,
                                 optionally blended with the two
                                 pre-existing unscoped predictors in
                                 PHASE_17_7_INTELLIGENCE and
                                 PHASE_18_9_1_AI_EVOLUTION
    intent_confidence.py      - combines/decays/calibrates raw scores
                                 from the other modules into one number
    intent_predictor.py       - single entry point tying all of the
                                 above together

Usage:
    from intelligence.intent_prediction import get_intent_predictor
    ip = get_intent_predictor()
    ip.record_observation("opened_vscode", "coding")
    ip.predict()   # -> ranked intents, predicted next action, active goals

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through the top-level predictor.

Purely additive - nothing in Phase 1-19.1 imports from here.
"""

from intelligence.intent_prediction.context_intent_mapper import ContextIntentMapper, get_context_intent_mapper
from intelligence.intent_prediction.goal_predictor import GoalPredictor, get_goal_predictor
from intelligence.intent_prediction.intent_confidence import IntentConfidence, get_intent_confidence
from intelligence.intent_prediction.intent_predictor import IntentPredictor, get_intent_predictor
from intelligence.intent_prediction.next_action_predictor import NextActionPredictor, get_next_action_predictor
from intelligence.intent_prediction.pattern_analyzer import PatternAnalyzer, get_pattern_analyzer

__all__ = [
    "IntentPredictor",
    "get_intent_predictor",
    "GoalPredictor",
    "get_goal_predictor",
    "NextActionPredictor",
    "get_next_action_predictor",
    "ContextIntentMapper",
    "get_context_intent_mapper",
    "PatternAnalyzer",
    "get_pattern_analyzer",
    "IntentConfidence",
    "get_intent_confidence",
]
