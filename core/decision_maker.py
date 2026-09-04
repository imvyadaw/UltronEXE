"""
Decision maker
==============
PHASE_17_2's intent_resolver already answers "is this a GOAL or not" -
a binary, and deliberately conservative one (see its own docstring).
Once something *is* a GOAL, though, autonomous_executor offers two very
different ways to run it (quick=True: one LLM plan + one critique pass,
vs quick=False: sub-goal decomposition with per-sub-goal retries) and,
until now, nothing decided between them except whatever the caller
happened to pass. This module is that missing decision:

    quick vs full   - a short, single-action goal ("close all Chrome
                       tabs") doesn't need sub-goal decomposition; a
                       multi-part one ("clean up Downloads and email me
                       a summary") does. Decided by cheap heuristics
                       (length, conjunctions, imperative count) -
                       deliberately not another LLM round-trip just to
                       decide how many other LLM round-trips to spend.
    run vs clarify  - consciousness.py's rolling confidence is folded
                       in: if Ultron has been getting things wrong
                       lately (confidence below CONFIDENCE_CLARIFY_BELOW)
                       *and* the goal text itself is short/ambiguous
                       (few words, no clear object), this routes to
                       "clarify" - one question back to the user -
                       instead of quietly burning a multi-step
                       autonomous run on a guess. A goal that's long
                       and specific is trusted even at lower confidence,
                       since ambiguity - not low confidence alone - is
                       what clarifying actually fixes.

Every decision carries a `reasoning` list of short strings explaining
which rule fired - this is meant to be legible in a debug console or a
"why did you do that" follow-up, not a black box.

Execution itself is still 100% autonomous_executor's - this module
never calls a tool. It decides *whether and how* to call
autonomous_executor, records the attempt on consciousness.py (focus +
outcome), and returns the result.
"""

from typing import Dict, List, Optional

from cognitive_core.intent_resolver import classify as resolve_intent

from core.consciousness_p18 import get_consciousness
from core.personality import get_personality

CONFIDENCE_CLARIFY_BELOW = 0.4
MIN_WORDS_FOR_TRUSTED_GOAL = 5  # a longer goal is treated as specific even at low confidence
CONJUNCTION_MARKERS = (" and ", " then ", " after that ", " aur ", " uske baad ")
MAX_QUICK_ACTIONS = 1  # more than this many implied actions -> full pipeline


def _estimate_actions(goal: str) -> int:
    """Cheap proxy for "how many distinct things is this asking for" -
    counts conjunction markers plus 1. Not NLP - just enough signal to
    tell "close Chrome" (1) from "close Chrome and email me a summary
    and back up my Downloads" (3), without spending an LLM call on it."""
    lowered = f" {goal.lower()} "
    return 1 + sum(lowered.count(marker) for marker in CONJUNCTION_MARKERS)


def _looks_specific(goal: str) -> bool:
    """A goal with enough words to name a clear object/target is
    trusted even when confidence is currently low - ambiguity is what
    clarify exists to fix, not low confidence by itself."""
    return len(goal.split()) >= MIN_WORDS_FOR_TRUSTED_GOAL


class DecisionMaker:
    """Routes resolved GOAL intents to quick / full / clarify. Use
    get_decision_maker()."""

    def __init__(self):
        self._consciousness = get_consciousness()
        self._personality = get_personality()

    def decide(self, text: str) -> Dict:
        """Doesn't execute anything - just returns the routing decision:
        {"route": "goal_quick" | "goal_full" | "clarify" | "delegate",
         "goal": str | None, "reasoning": [str, ...],
         "confidence_used": float, "clarify_question": str | None}.
        Non-GOAL text (intent_resolver falls through to CHAT/WORKFLOW/
        etc.) always routes "delegate" - this module only has an
        opinion about GOAL-shaped requests."""
        reasoning: List[str] = []
        resolved = resolve_intent(text)

        if resolved.intent != "goal":
            reasoning.append(f"intent_resolver classified this as '{resolved.intent}', not a goal")
            return {
                "route": "delegate",
                "goal": None,
                "reasoning": reasoning,
                "confidence_used": None,
                "clarify_question": None,
            }

        goal = resolved.payload["goal"]
        confidence = self._consciousness.confidence
        reasoning.append(f"resolved as goal: '{goal}'")
        reasoning.append(f"current confidence (trailing outcomes): {confidence}")

        specific = _looks_specific(goal)
        if confidence < CONFIDENCE_CLARIFY_BELOW and not specific:
            reasoning.append(
                f"confidence below {CONFIDENCE_CLARIFY_BELOW} and goal reads as short/ambiguous "
                f"(<{MIN_WORDS_FOR_TRUSTED_GOAL} words) - asking instead of guessing"
            )
            question = self._clarify_question(goal)
            return {
                "route": "clarify",
                "goal": goal,
                "reasoning": reasoning,
                "confidence_used": confidence,
                "clarify_question": question,
            }
        if confidence < CONFIDENCE_CLARIFY_BELOW and specific:
            reasoning.append("confidence is low but the goal is specific enough to trust anyway")

        actions = _estimate_actions(goal)
        reasoning.append(f"estimated distinct actions implied: {actions}")
        if actions <= MAX_QUICK_ACTIONS:
            reasoning.append("single-action goal - routing quick (one plan, one critique pass)")
            return {
                "route": "goal_quick",
                "goal": goal,
                "reasoning": reasoning,
                "confidence_used": confidence,
                "clarify_question": None,
            }

        reasoning.append("multi-action goal - routing full (sub-goal decomposition with retries)")
        return {
            "route": "goal_full",
            "goal": goal,
            "reasoning": reasoning,
            "confidence_used": confidence,
            "clarify_question": None,
        }

    def decide_and_execute(self, text: str) -> Dict:
        """decide() plus actually carrying it out for the goal routes -
        pushes/pops consciousness focus around the run and feeds the
        critique result back in via note_outcome(), so the *next*
        decide() call already reflects how this one went. Non-goal and
        clarify routes are returned as-is (nothing to execute for
        clarify; delegate is the caller's job, same contract as
        intent_resolver.route())."""
        decision = self.decide(text)
        if decision["route"] in ("delegate", "clarify"):
            return decision

        from cognitive_core.autonomous_executor import get_autonomous_executor

        executor = get_autonomous_executor()
        goal = decision["goal"]
        quick = decision["route"] == "goal_quick"

        self._consciousness.push_focus(goal, source="decision_maker")
        try:
            outcome = executor.run_goal(goal, quick=quick)
        finally:
            self._consciousness.pop_focus()

        satisfied = outcome.get("satisfied", False)
        self._consciousness.note_outcome(satisfied, detail=goal if not satisfied else "")

        decision["outcome"] = outcome
        decision["style"] = self._personality.current_style()
        return decision

    def _clarify_question(self, goal: str) -> str:
        """A short, honest ask-back rather than a guess - phrased
        through personality.speak() so it still sounds like Ultron, not
        a bare error string. Falls back to a plain sentence if
        personality/tone_manager has no matching phrase category."""
        phrase = self._personality.speak(
            "general_concern", message=f'I want to get this right - could you say a bit more about "{goal}"?'
        )
        return phrase.get("text") or f'Could you say a bit more about what you mean by "{goal}"?'


_decision_maker: Optional[DecisionMaker] = None


def get_decision_maker() -> DecisionMaker:
    global _decision_maker
    if _decision_maker is None:
        _decision_maker = DecisionMaker()
    return _decision_maker
