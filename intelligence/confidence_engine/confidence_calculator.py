"""
Confidence Calculator (Phase 19.8 - Confidence Engine)
==================================================
Turns a handful of independent signals about a pending decision into
one confidence score in [0, 1]. Signals are supplied by whatever's
calling in (source_reliability, historical_success_rate, ambiguity,
model_self_confidence, ...) - this module doesn't go find them
itself, it just combines whichever ones it's given. Missing signals
don't drag the score toward 0; they're simply left out and the
remaining weights are renormalized, so a caller with only one signal
still gets a sensible score built from that signal alone rather than
a penalized one.

Stateless: no persistence, same as skill_generator.py in Phase 19.6 -
this module only computes, it never decides what to do with the
result (decision_gate.py's job) or tracks whether past scores were
actually right (confidence_learner.py's job).
"""

import threading
from typing import Dict, Optional

_instance: Optional["ConfidenceCalculator"] = None
_instance_lock = threading.Lock()

# default weight per signal when the caller doesn't override them;
# "ambiguity" is inverted (1 - ambiguity) before weighting since higher
# ambiguity should pull confidence down, not up
_DEFAULT_WEIGHTS = {
    "source_reliability": 0.30,
    "historical_success_rate": 0.30,
    "ambiguity": 0.25,
    "model_self_confidence": 0.15,
}

_INVERTED_SIGNALS = {"ambiguity"}


# a signal supplied outside [0, 1] is almost certainly a caller bug -
# clamp rather than let it silently skew the whole score
def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class ConfidenceCalculator:
    """signals dict -> {"confidence", "signals_used", "reasons"}."""

    def calculate(self, signals: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> Dict:
        weights = weights or _DEFAULT_WEIGHTS
        usable = {k: v for k, v in signals.items() if k in weights and v is not None}

        if not usable:
            return {
                "confidence": 0.5,
                "signals_used": {},
                "reasons": ["no recognized signals supplied - defaulting to neutral 0.5"],
            }

        total_weight = sum(weights[k] for k in usable)
        weighted_sum = 0.0
        reasons = []
        for key, raw_value in usable.items():
            value = _clamp(float(raw_value))
            effective = (1.0 - value) if key in _INVERTED_SIGNALS else value
            share = weights[key] / total_weight
            weighted_sum += effective * share
            reasons.append(f"{key}={value:.2f} (weight {share:.2f})")

        confidence = _clamp(weighted_sum)
        return {"confidence": confidence, "signals_used": usable, "reasons": reasons}

    @staticmethod
    def source_reliability_signal(name: str, url: Optional[str] = None) -> float:
        """learning/source_validator.py's trust_score for a named source,
        already in [0, 1] and shaped exactly like this module's own
        "source_reliability" signal - callers that only have a source
        name/url (not a pre-computed reliability number) can use this to
        fill that slot in calculate()'s signals dict instead of guessing.
        Falls back to the validator's own neutral default (0.5) if the
        validator isn't available or the lookup fails, same as a missing
        signal already degrades to in calculate()."""
        try:
            from learning.source_validator import SourceValidator

            verdict = SourceValidator().validate(name=name, url=url)
            if isinstance(verdict, dict) and "error" not in verdict:
                return _clamp(float(verdict.get("trust_score", 0.5)))
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("intelligence.confidence_engine.confidence_calculator.source_reliability_signal")
        return 0.5

    @staticmethod
    def calculate_fact_confidence(
        extraction_confidence: float, source_trust: float, corroborating_sources: int = 1
    ) -> Dict:
        """Sibling entry point to calculate() for the other kind of
        confidence this project scores: not "how sure should I be before
        acting/answering" (calculate()'s job), but "how sure am I that a
        specific extracted *fact* is true" - delegates straight to
        learning/confidence.py's score()/classify(), which already has
        this exact, deliberately-simple corroboration-aware math (see that
        module's docstring). Kept as a thin pass-through rather than
        duplicated here, so the two confidence notions stay reachable from
        one place (this engine) without collapsing into one set of
        weights that would need to make sense for both decision-confidence
        and fact-confidence at once.

        Returns {"confidence": float, "label": str} on success, or a
        neutral fallback ({"confidence": 0.5, "label": "medium"}) if
        learning/confidence.py can't be imported."""
        try:
            from learning.confidence import score as fact_score, classify as fact_classify

            confidence = fact_score(extraction_confidence, source_trust, corroborating_sources)
            return {"confidence": confidence, "label": fact_classify(confidence)}
        except Exception:
            return {"confidence": 0.5, "label": "medium"}

    @staticmethod
    def quick_estimate(known: bool, has_precedent: bool, ambiguous: bool) -> Dict:
        """Cheap fallback for callers with no real signals to hand
        over, just three yes/no judgments - useful when the full
        calculate() inputs simply aren't available yet."""
        signals = {
            "source_reliability": 0.8 if known else 0.4,
            "historical_success_rate": 0.75 if has_precedent else 0.5,
            "ambiguity": 0.7 if ambiguous else 0.15,
        }
        calculator = get_confidence_calculator()
        return calculator.calculate(signals)


def get_confidence_calculator() -> ConfidenceCalculator:
    """Process-wide ConfidenceCalculator singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConfidenceCalculator()
    return _instance
