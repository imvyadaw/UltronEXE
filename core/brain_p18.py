"""
Brain (Phase 18)
================
Same relationship to core/brain.py that PHASE_17_1's phase16_bridge.py
has to Phase 16: not a replacement, a single gathering point. core.brain
.get_brain() still owns the actual LLM plumbing (cloud/local routing,
retries, history) and nothing here duplicates that.

What Phase 18 adds is the layer *above* the LLM call: given raw text,
decide what kind of request this is and how it should be handled before
ever reaching a model, using everything Phase 17-18 now track that
core.brain has no idea about:

    decision_maker.decide_and_execute(text)
        -> non-goal text: delegates to intent_resolver.route(), which
           itself falls through to core.intent_router.route() for plain
           chat - i.e. ordinary conversation still goes straight to
           core.brain via the exact same path it always did.
        -> goal text: routed quick/full/clarify per current confidence
           (consciousness.py) and executed via autonomous_executor,
           with the attempt recorded back onto consciousness so the
           next decision benefits from it.

    personality.speak(...)
        -> any Ultron-initiated line (not a direct answer to a
           question) goes through here so tone stays consistent with
           the user's current mood trend, not just per-category static
           text.

get_brain() below returns the same AIRouter core.brain always returned
- kept for any caller that only wants the raw LLM object and doesn't
need the Phase 18 layer. get_ultron() is the new, recommended entry
point for anything upstream of a raw model call.
"""

from typing import Callable, Dict, Optional

from core.brain import get_brain as _get_core_brain
from core.logger import get_logger

from core.consciousness_p18 import get_consciousness
from core.decision_maker import get_decision_maker
from core.personality import get_personality

logger = get_logger("ultron.phase18.brain")


def get_brain():
    """Unchanged passthrough to core.brain.get_brain() (the AIRouter) -
    kept so existing callers that only need the raw model don't have to
    change. Prefer get_ultron().think() for anything that should get
    the Phase 18 goal-routing/personality/introspection layer."""
    return _get_core_brain()


class Ultron:
    """The Phase 18 front door. Do not construct directly - use get_ultron()."""

    def __init__(self):
        self.core_brain = _get_core_brain()
        self.consciousness = get_consciousness()
        self.decision_maker = get_decision_maker()
        self.personality = get_personality()

    def think(self, text: str, chat_fn: Optional[Callable[[str], str]] = None) -> Dict:
        """Single entry point for one turn of input. Returns:
        {"response": str, "route": str, "reasoning": [...],
         "state": <consciousness.reflect() snapshot>}. Never raises -
        an internal failure degrades to routing straight through to
        core_brain.chat(text) rather than leaving the caller with
        nothing, matching every other Ultron execution path.
        """
        try:
            decision = self.decision_maker.decide_and_execute(text)
        except Exception as e:
            logger.error(f"decision_maker failed, falling back to plain chat: {e}")
            return {
                "response": self.core_brain.chat(text),
                "route": "fallback_chat",
                "reasoning": [f"decision_maker raised: {e}"],
                "state": self.consciousness.reflect(),
            }

        route = decision["route"]

        if route == "clarify":
            response = decision["clarify_question"]
        elif route in ("goal_quick", "goal_full"):
            outcome = decision.get("outcome", {})
            response = self._response_for_goal_outcome(decision["goal"], outcome)
        else:  # "delegate" - not a goal, hand off to the normal chat/intent path
            from cognitive_core.intent_resolver import route as resolve_route

            result = resolve_route(text, chat_fn=chat_fn or self.core_brain.chat, run_async=False)
            response = result.response

        return {
            "response": response,
            "route": route,
            "reasoning": decision.get("reasoning", []),
            "state": self.consciousness.reflect(),
        }

    def _response_for_goal_outcome(self, goal: str, outcome: Dict) -> str:
        if "error" in outcome:
            return self.personality.speak(
                "general_concern", message=f"I ran into trouble on \"{goal}\": {outcome['error']}"
            )["text"]
        if outcome.get("satisfied"):
            return (
                self.personality.speak("goal_complete", goal=goal)
                if self._has_category("goal_complete")
                else f"Done - '{goal}' looks achieved."
            )
        reason = outcome.get("stopped_reason") or "couldn't fully confirm it worked"
        return f"I made progress on '{goal}' but {reason}."

    def _has_category(self, category: str) -> bool:
        try:
            from proactive.personality.ultron_phrases import get_phrases

            return bool(get_phrases(category))
        except Exception:
            return False

    def health_check(self) -> Dict:
        """Cheap startup sanity check, same idea as
        phase16_bridge.Phase16Bridge.health_check()."""
        try:
            self.core_brain.chat_with_tools  # attribute presence check only, no call
            brain_ok = True
        except Exception:
            brain_ok = False
        return {
            "core_brain_ok": brain_ok,
            "consciousness_state": self.consciousness.reflect(),
            "personality_traits": self.personality.traits,
        }


_ultron: Optional[Ultron] = None


def get_ultron() -> Ultron:
    global _ultron
    if _ultron is None:
        _ultron = Ultron()
    return _ultron
