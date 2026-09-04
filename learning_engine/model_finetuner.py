"""
model_finetuner.py
=====================
NOTE ON SCOPE: "finetuner" here does not mean gradient-descent
finetuning of the LLM itself - shipping an automatic pipeline that
silently uploads a user's private conversation history to retrain a
hosted model is not something this module does. What it *does* do is
tune the small local, transparent numeric parameters that the rest
of ULTRON's intelligence layer relies on:

  - NextActionPredictor's transition_weight / time_weight blend
  - ReinforcementLearner's per-action preference scores
  - AnomalyDetector's sensitivity thresholds

...using FeedbackCollector's scored history as the training signal.
Every adjustment is small, bounded, logged, and reversible via
`reset_to_defaults()`. If you later want to wire in genuine LLM
finetuning (e.g. an OpenAI/Anthropic finetuning job on your own
exported, consented data), that belongs in its own explicit,
user-initiated skill - not silently inside the background loop.

Dependencies: none beyond the standard library + feedback_collector.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, asdict
from pathlib import Path

from .feedback_collector import FeedbackCollector

logger = logging.getLogger("ultron.model_finetuner")

DEFAULT_STORE = Path("ultron_data/learning/tuned_params.json")

DEFAULTS = {
    "transition_weight": 0.65,
    "time_weight": 0.35,
    "anomaly_sensitivity": 1.0,  # multiplier on AnomalyDetector's z-score thresholds
}

_STEP = 0.02
_BOUNDS = {
    "transition_weight": (0.2, 0.9),
    "time_weight": (0.1, 0.8),
    "anomaly_sensitivity": (0.5, 2.0),
}


@dataclass
class TunedParams:
    transition_weight: float = DEFAULTS["transition_weight"]
    time_weight: float = DEFAULTS["time_weight"]
    anomaly_sensitivity: float = DEFAULTS["anomaly_sensitivity"]


class ModelFinetuner:
    """Nudges small numeric hyperparameters based on aggregated feedback scores."""

    def __init__(self, feedback: FeedbackCollector, store_path: Path = DEFAULT_STORE):
        self.feedback = feedback
        self.store_path = Path(store_path)
        self._lock = threading.Lock()
        self.params = TunedParams()
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.params = TunedParams(**data)
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load tuned params (%s), using defaults", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.params), indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    def _clamp(self, name: str, value: float) -> float:
        lo, hi = _BOUNDS[name]
        return max(lo, min(hi, value))

    def step_from_feedback(self, action: str):
        """
        A single small, bounded adjustment step based on the net feedback
        score for `action`. Positive net feedback nudges transition_weight
        up slightly (predictions were useful); negative feedback nudges it
        down and time_weight up instead (fall back more on time-of-day
        patterns rather than 'what usually happens after this').
        """
        score = self.feedback.score_for_action(action)  # in [-1, 1]
        with self._lock:
            if score > 0.2:
                self.params.transition_weight = self._clamp(
                    "transition_weight", self.params.transition_weight + _STEP * score
                )
            elif score < -0.2:
                self.params.transition_weight = self._clamp(
                    "transition_weight", self.params.transition_weight + _STEP * score
                )
                self.params.time_weight = self._clamp("time_weight", self.params.time_weight - _STEP * score)
            self._save()
        logger.info("Tuned params after feedback on '%s' (score=%.2f): %s", action, score, self.params)
        return self.params

    def reset_to_defaults(self):
        with self._lock:
            self.params = TunedParams()
            self._save()
        logger.info("Tuned params reset to defaults")
        return self.params


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fc = FeedbackCollector(store_path=Path("ultron_data/learning/_demo_feedback_log.json"))
    tuner = ModelFinetuner(fc, store_path=Path("ultron_data/learning/_demo_tuned_params.json"))
    print(tuner.step_from_feedback("run_skill:whatsapp_send"))
