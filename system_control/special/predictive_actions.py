"""Predictive Actions Control
==============================
Control surface over proactive/predictor.py (ActionPredictor - learns
time/sequence patterns) and proactive/automatic_actions.py
(AutomaticActionExecutor - runs an already-approved suggestion,
cooldown-gated). Neither module exposes a simple "what's coming up /
should I approve auto-execution" view; this wraps both plus
proactive/suggester.py (phrases a prediction into a human suggestion)
into that single control surface, and owns the confidence threshold
above which suggestions are allowed to auto-execute instead of asking.

Raising the auto-execute threshold or approving an action for
auto-execution going forward are confirm-gated - they change what
happens on this machine without asking each time.
"""
import logging

import json
from pathlib import Path
from typing import Dict, Optional

_CONFIG_PATH = Path(__file__).resolve().parent / "_predictive_config.json"
_DEFAULT_THRESHOLD = 0.75


class PredictiveActionsControl:
    def _load_config(self) -> Dict:
        if _CONFIG_PATH.exists():
            try:
                return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
        return {"auto_execute_threshold": _DEFAULT_THRESHOLD}

    def _save_config(self, cfg: Dict) -> None:
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    def get_predictions(self, context: Optional[Dict] = None, top_k: int = 3) -> Dict:
        from proactive.predictor import get_action_predictor

        preds = get_action_predictor().predict_next(context=context, top_k=top_k)
        return {"predictions": preds}

    def get_routine_prediction(self, min_confidence: float = 0.5) -> Dict:
        from proactive.predictor import get_action_predictor

        pred = get_action_predictor().predict_routine(min_confidence=min_confidence)
        return {"prediction": pred}

    def get_suggestions(self, context: Optional[Dict] = None, top_k: int = 3) -> Dict:
        """Human-phrased suggestions (via proactive.suggester), each tagged
        with whether it clears the current auto-execute threshold."""
        from proactive.suggester import get_suggestion_engine

        suggestions = get_suggestion_engine().generate(context=context, top_k=top_k)
        threshold = self._load_config().get("auto_execute_threshold", _DEFAULT_THRESHOLD)
        for s in suggestions:
            s["clears_auto_execute_threshold"] = s.get("confidence", 0) >= threshold
        return {"suggestions": suggestions, "auto_execute_threshold": threshold}

    def approve_and_execute(self, suggestion: Dict) -> Dict:
        """Run one suggestion right now via AutomaticActionExecutor - its
        own cooldown/allow-list logic still applies, this doesn't bypass it."""
        from proactive.automatic_actions import get_automatic_action_executor

        return get_automatic_action_executor().consider(suggestion)

    def dismiss(self, action_name: str) -> Dict:
        from proactive.automatic_actions import get_automatic_action_executor

        get_automatic_action_executor().disallow_action(action_name)
        return {"success": True, "dismissed": action_name}

    def set_auto_execute_for_action(self, action_name: str, allowed: bool, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'allow' if allowed else 'stop allowing'} '{action_name}' to auto-execute without asking each time.",
            }
        from proactive.automatic_actions import get_automatic_action_executor

        executor = get_automatic_action_executor()
        if allowed:
            executor.allow_action(action_name)
        else:
            executor.disallow_action(action_name)
        return {"success": True, "action_name": action_name, "auto_execute_allowed": allowed}

    def list_auto_execute_actions(self) -> Dict:
        from proactive.automatic_actions import get_automatic_action_executor

        return {"allowed_actions": sorted(get_automatic_action_executor().list_allowed())}

    def get_auto_execute_threshold(self) -> Dict:
        return {"auto_execute_threshold": self._load_config().get("auto_execute_threshold", _DEFAULT_THRESHOLD)}

    def set_auto_execute_threshold(self, threshold: float, confirm: bool = False) -> Dict:
        if not (0.0 <= threshold <= 1.0):
            return {"error": "threshold must be between 0.0 and 1.0"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set the auto-execute confidence threshold to {threshold} - predictions at or above this run without asking.",
            }
        cfg = self._load_config()
        cfg["auto_execute_threshold"] = threshold
        self._save_config(cfg)
        return {"success": True, "auto_execute_threshold": threshold}


_instance: Optional[PredictiveActionsControl] = None


def get_predictive_actions_control() -> PredictiveActionsControl:
    global _instance
    if _instance is None:
        _instance = PredictiveActionsControl()
    return _instance
