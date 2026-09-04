"""
AI Supercharger
===============
Two complementary upgrades that sit ON TOP of ai/ai_router.py without
changing its public interface:

  - multi_model_ensemble.py: fires the SAME prompt at several already-
    configured cloud backends at once and combines/votes on the
    replies into one best answer, instead of using whichever single
    backend the router happened to pick.
  - dynamic_model_switcher.py: a smarter "which backend/model for THIS
    turn" decision than ai_router's plain fallback-order chain -
    reuses ai/complexity_router.py's tiering and each client's
    conversation_history, adding a scored choice + a short-lived
    forced override.

Neither module talks to a network client directly - both go through
ai.ai_router.get_router() so history sharing, retry policy and offline
fallback stay exactly as ai_router.py already implements them.
"""

from ai_supercharger.multi_model_ensemble import get_ensemble_response
from ai_supercharger.dynamic_model_switcher import choose_backend, force_backend, clear_override

__all__ = ["get_ensemble_response", "choose_backend", "force_backend", "clear_override"]
