"""
Predictive Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Thin, defensive bridge onto intelligence.predictive_preparation
(Phase 20.2) - the package that decides what ULTRON should have
*ready* (next_task_predictor.py, app_preloader.py, model_preloader.py,
context_preloader.py, resource_optimizer.py, per Phase 20.3's own
docstrings), fronted by its own predictive_engine.py orchestrator the
same way performance_engine.py fronts adaptive_performance/. That
orchestrator's exact class/getter names aren't known here, so this
still resolves defensively rather than assuming them - see
_bridge_utils.py.

Usage:
    from intelligence_bridge.predictive_bridge import get_predictive_bridge

    prb = get_predictive_bridge()
    if prb.is_available():
        prediction = prb.predict_next(context={"world_state": ...})

Purely additive - every method here is a best-effort call that returns
None on failure instead of raising.
"""

from typing import Any, Dict, Optional

from intelligence_bridge._bridge_utils import (
    first_success,
    resolve_module,
    resolve_singleton,
    safe_call,
    logger,
)

_CANDIDATE_MODULES = (
    "intelligence.predictive_preparation.predictive_engine",
    "intelligence.predictive_preparation",
    "intelligence.predictive",
)
_KEYWORDS = ("predict",)
_GETTER_NAMES = ("get_predictive_engine", "get_predictive_preparation")
_CLASS_NAMES = ("PredictiveEngine", "PredictivePreparation")


class PredictiveBridge:
    """Bridges to intelligence.predictive_preparation (Phase 20.2)."""

    def __init__(self):
        self._module = resolve_module(_CANDIDATE_MODULES, _KEYWORDS)
        self._instance = resolve_singleton(self._module, _GETTER_NAMES, _CLASS_NAMES)
        if self._instance is not None:
            logger.info("[predictive_bridge] connected to %s", getattr(self._module, "__name__", "?"))
        else:
            logger.info("[predictive_bridge] predictive_preparation not found - running in degraded/no-op mode")

    def is_available(self) -> bool:
        return self._instance is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "predictive",
            "available": self.is_available(),
            "source_module": getattr(self._module, "__name__", None),
        }

    def predict_next(self, context: Optional[Dict] = None, *args, **kwargs) -> Optional[Any]:
        """Best-effort prediction of the user's next likely task/need.
        Phase 20.2's PredictiveEngine's one entry point is
        predict_and_prepare(current_task=, context=, session_id=), not
        predict_next()/predict() directly, so this shims onto it when
        the generic candidates below don't match."""
        result = first_success(
            self._instance,
            ("predict_next", "predict", "predict_next_task"),
            context,
            *args,
            **kwargs,
        )
        if result is not None:
            return result
        if hasattr(self._instance, "predict_and_prepare"):
            return safe_call(self._instance, "predict_and_prepare", context=context)
        return None

    def prepare(self, context: Optional[Dict] = None, *args, **kwargs) -> Optional[Any]:
        """Best-effort hand-off to preload whatever the prediction says
        will likely be needed (apps/models/context)."""
        return first_success(
            self._instance,
            ("prepare", "preload", "warm_up"),
            context,
            *args,
            **kwargs,
        )

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough for anything not covered above."""
        return safe_call(self._instance, method_name, *args, **kwargs)


_bridge_instance: Optional[PredictiveBridge] = None


def get_predictive_bridge() -> PredictiveBridge:
    """Process-wide PredictiveBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = PredictiveBridge()
    return _bridge_instance
