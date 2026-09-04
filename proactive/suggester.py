"""
Suggester (Phase 25 - Proactive Automation)
=============================================
Turns proactive/predictor.py's "what's likely" into "what, if
anything, is worth actually telling the user (or doing for them)".
Sits between predictor.py and both proactive/engine.py's delivery path
and proactive/automatic_actions.py's execution path:

    predictor.predict_next()  -->  suggester.generate()  -->  engine._deliver()
                                                          `--> automatic_actions.consider()

A prediction only becomes a suggestion if it (a) clears MIN_SUGGEST_CONFIDENCE
and (b) maps to something Ultron can actually do - i.e. it's a registered
capability in core.capability_registry. A confident-but-unactionable
prediction (predictor learned a pattern for an action name that was
since removed/renamed) is silently dropped rather than surfaced as a
suggestion nobody can act on.

Each suggestion also carries a `risk` derived from the capability's
permission_level ("normal" -> "low", "elevated"/"destructive" ->
matching name) and an `auto_eligible` flag (risk == "low" and
confidence >= AUTO_ELIGIBLE_CONFIDENCE) that automatic_actions.py uses
to decide whether it's even allowed to consider auto-running it -
elevated/destructive predictions are never auto-eligible no matter how
confident the pattern is; they can only ever be suggested.
"""

from typing import Dict, List, Optional

from proactive.predictor import get_action_predictor
from core.logger import get_logger

logger = get_logger("ultron.proactive.suggester")

MIN_SUGGEST_CONFIDENCE = 0.5
AUTO_ELIGIBLE_CONFIDENCE = 0.75
MAX_SUGGESTIONS_PER_TICK = 2

_RISK_BY_PERMISSION = {"normal": "low", "elevated": "elevated", "destructive": "destructive"}


class SuggestionEngine:
    """predict -> filter against capability_registry -> phrase -> rank."""

    def __init__(self):
        self._predictor = get_action_predictor()

    def generate(self, context: Optional[Dict] = None, top_k: int = MAX_SUGGESTIONS_PER_TICK) -> List[Dict]:
        """Returns up to `top_k` suggestion dicts:
        {"category", "action_name", "arguments", "confidence", "risk",
         "auto_eligible", "text", "basis"}. Empty list is the normal,
        common case - most ticks have nothing confident enough to say."""
        predictions = self._predictor.predict_next(context=context, top_k=top_k * 3)
        suggestions: List[Dict] = []

        for pred in predictions:
            if pred["confidence"] < MIN_SUGGEST_CONFIDENCE:
                continue
            capability = self._resolve_capability(pred["action_name"])
            if capability is None:
                logger.debug(f"Dropping prediction for unknown capability '{pred['action_name']}'.")
                continue

            risk = _RISK_BY_PERMISSION.get(capability.permission_level, "elevated")
            auto_eligible = risk == "low" and pred["confidence"] >= AUTO_ELIGIBLE_CONFIDENCE
            suggestions.append(
                {
                    "category": "proactive_suggestion",
                    "action_name": pred["action_name"],
                    "arguments": {},
                    "confidence": pred["confidence"],
                    "risk": risk,
                    "auto_eligible": auto_eligible,
                    "basis": pred["basis"],
                    "text": self._phrase(capability, pred),
                }
            )
            if len(suggestions) >= top_k:
                break

        return suggestions

    def _resolve_capability(self, action_name: str):
        try:
            from core.capability_registry import get_capability_registry

            registry = get_capability_registry()
            capability = registry.get(action_name)
            if capability is not None and capability.enabled:
                return capability
        except Exception as e:
            logger.debug(f"Capability lookup failed for '{action_name}': {e}")
        return None

    def _phrase(self, capability, pred: Dict) -> str:
        label = (capability.description or capability.name).strip().rstrip(".")
        if pred["basis"] == "time_pattern":
            return f"Sir, you usually {label.lower()} around this time - shall I go ahead?"
        return f"Sir, you often {label.lower()} next - want me to take care of it?"


_engine: Optional[SuggestionEngine] = None


def get_suggestion_engine() -> SuggestionEngine:
    global _engine
    if _engine is None:
        _engine = SuggestionEngine()
    return _engine
