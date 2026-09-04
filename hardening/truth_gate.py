"""
Truth gate
==========
Sits between the verification engine (what actually happened, per tool
call, this turn - see verification_engine/) and the response text (what
the model told the user happened) and decides whether the two agree.

Reuses stability.truth_prompt_contract.check_turn() for its
regex-based "does the response text contain unearned completion language"
signal (that logic already exists and works - no reason to re-implement
it) and adds a second, independent signal on top: does the *verified*
per-call ResultState actually support what the response claims. A turn can
pass 29-A's regex check (the response text just doesn't happen to contain
any of its CLAIM_PATTERNS) and still deserve a flag here - e.g. a chained
open_application -> type_into_ui_element -> send_message turn where the
last step verifies as PARTIAL_SUCCESS but the model's phrasing is vague
enough that no pattern matches it.

Same "advisory, never blocks" stance as 29-A: evaluate() never raises and
never mutates the response - it produces a verdict for
response_truth_guard.py to log/act on.

Strict truth gate (claim policy)
---------------------------------
Alongside the mismatch-detection above, evaluate() also classifies the
turn-level ResultState into one of four claim policies - what kind of
claim the response text is actually entitled to make, independent of
whether this particular response happened to earn a mismatch flag:

    VERIFIED_SUCCESS  -> "allowed"             - a definitive success claim is earned.
    PARTIAL_SUCCESS   -> "partial_only"         - only a qualified/partial claim is earned.
    VERIFIED_FAILURE  -> "blocked_success"      - a success claim is not earned; failure should be stated.
    UNKNOWN           -> "blocked_definitive"   - neither a success nor a failure claim is earned.

Same advisory stance as everything else in this module: CLAIM_POLICY is
information for a caller to act on (e.g. to steer a follow-up rephrase, or
just to log alongside the mismatch list) - evaluate() itself still never
rewrites or withholds response_text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from stability.truth_prompt_contract import TruthCheckResult, check_turn

from .evidence_collector import TurnEvidence
from .result_states import ResultState
from .verification_engine import TurnVerification

# See "Strict truth gate (claim policy)" above for what each value means.
CLAIM_POLICY: Dict[ResultState, str] = {
    ResultState.VERIFIED_SUCCESS: "allowed",
    ResultState.PARTIAL_SUCCESS: "partial_only",
    ResultState.VERIFIED_FAILURE: "blocked_success",
    ResultState.UNKNOWN: "blocked_definitive",
}


def claim_policy(state: ResultState) -> str:
    """The claim policy for a single ResultState - see CLAIM_POLICY.
    Falls back to the most conservative policy ("blocked_definitive") for
    any value this module doesn't recognize, rather than raising."""
    return CLAIM_POLICY.get(state, "blocked_definitive")


@dataclass
class TruthGateVerdict:
    ok: bool
    turn_state: ResultState
    regex_check: TruthCheckResult
    mismatches: List[str] = field(default_factory=list)

    @property
    def claim_policy(self) -> str:
        """What kind of claim turn_state actually entitles the response
        to make - see CLAIM_POLICY above."""
        return claim_policy(self.turn_state)

    def summary(self) -> str:
        if self.ok:
            return f"truth gate: ok (turn_state={self.turn_state.value}, claim_policy={self.claim_policy})"
        lines = [f"truth gate: FLAGGED (turn_state={self.turn_state.value}, claim_policy={self.claim_policy})"]
        for m in self.mismatches:
            lines.append(f"  - {m}")
        if not self.regex_check.ok:
            lines.append(f"  - {self.regex_check.summary()}")
        return "\n".join(lines)


def evaluate(response_text: str, evidence: TurnEvidence, verification: TurnVerification) -> TruthGateVerdict:
    """Never raises - an internal failure degrades to an ok=True verdict
    rather than being the reason a real response fails to return (the
    caller, response_truth_guard.guard_turn(), has its own outer safety
    net too, but this function shouldn't need it)."""
    try:
        tool_names = [c.tool_name for c in evidence.calls]
        # check_turn() wants {"success": bool, "error": ...}-shaped dicts;
        # NormalizedResult already reduced every call to exactly that
        # shape regardless of what the raw tool result originally looked
        # like, so this is just a field rename, not new logic.
        tool_result_dicts = [{"success": not c.result.is_error, "error": c.result.error} for c in evidence.calls]
        try:
            regex_result = check_turn(response_text, tool_names, tool_result_dicts)
        except Exception:
            regex_result = TruthCheckResult(ok=True)

        mismatches: List[str] = []
        for call in verification.calls:
            if call.outcome.state == ResultState.VERIFIED_FAILURE:
                # Very loose "did the response even gesture at this" check -
                # same bar 29-A's own unmentioned-error check uses, just
                # applied to the verified state rather than only the raw
                # {"error": ...} key.
                tool_hint = call.evidence.tool_name.replace("_", " ")
                if tool_hint.lower() not in (response_text or "").lower():
                    mismatches.append(
                        f"{call.evidence.tool_name} verified as VERIFIED_FAILURE ({call.outcome.reason}) "
                        "but the response doesn't appear to mention it"
                    )
            elif call.outcome.state == ResultState.PARTIAL_SUCCESS:
                mismatches.append(
                    f"{call.evidence.tool_name} only reached PARTIAL_SUCCESS ({call.outcome.reason}) - "
                    "worth confirming the response doesn't overstate it as fully done"
                )

            # learning/source_validator.py's trust verdict for this call
            # (see evidence_collector.py's _resolve_source_trust()) - flagged
            # here independently of the state-based checks above, so a
            # response that states a search/lookup result as flat fact still
            # gets a specific, traceable note about *why* it's shaky, even on
            # a call whose ResultState alone wouldn't have raised anything
            # (false_success_protection.py's principle 5 already downgrades
            # the state itself for a low-trust source; this is the
            # human-readable half of that same signal).
            source_trust = getattr(call.evidence, "source_trust", None)
            if source_trust is not None and source_trust < 0.35:
                mismatches.append(
                    f"{call.evidence.tool_name}'s cited source scored a low trust_score "
                    f"({source_trust:.2f}, tier={getattr(call.evidence, 'source_tier', None)}) via "
                    "learning/source_validator.py - worth confirming the response hedges rather than "
                    "stating it as settled fact"
                )

        ok = regex_result.ok and not mismatches
        return TruthGateVerdict(
            ok=ok, turn_state=verification.turn_state, regex_check=regex_result, mismatches=mismatches
        )
    except Exception:
        return TruthGateVerdict(ok=True, turn_state=ResultState.UNKNOWN, regex_check=TruthCheckResult(ok=True))
