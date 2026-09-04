"""
False-success protection
=========================
A cross-cutting safety net applied after verification_engine/ has already
run its per-tool-category checks (see verification_engine/verifiers.py),
on every CallVerification in a TurnVerification (see
verification_engine/__init__.py's verify_turn()). Where a domain verifier
answers "what does this specific tool's result mean", this module answers
a narrower, tool-agnostic question that applies no matter which of the ten
categories a call routed to:

    Is a bare success=True actually strong enough evidence to let a
    state-changing action's outcome stand as VERIFIED_SUCCESS?

Four principles, matching this project's own hard-won incidents (see
README.md's "Why this phase exists" - youtube_play, WhatsApp send_message,
confirm-gated shutdown - and /areas/ultron-assistant.md's phase log):

1. Never trust success=True alone.
   A tool's own success flag is self-reported. It says the call didn't
   raise and the tool believes it did what it was asked - it is not
   independent confirmation. verification_engine/'s domain verifiers
   already encode the *specific* known ways that can be wrong (typed vs
   sent, search page vs playback, confirm-gate skip). This module adds
   the *generic* version of the same doubt: a mutating action reporting
   success=True with zero result data to cross-check against gets
   downgraded, even when no domain verifier above had a specific rule for
   that tool.

2. Verify actual side effect, not just the call's return value.
   This module can't reach into Windows/the browser/a mic itself - that's
   what the ten domain verifiers exist for. What this module *can* do is
   refuse to let the absence of any side-effect evidence pass silently:
   `enforce()` looks at whether NormalizedResult.data contains anything
   at all for a mutating call, since "empty data" is exactly what a
   result that never actually checked its own side effect looks like.

3. Detect partial execution.
   Handled primarily by result_states.combine() at the turn level (a mix
   of per-call states folds to PARTIAL_SUCCESS) and by individual
   verifiers' chained-step checks. This module adds one more shape:
   a mutating call that came back VERIFIED_SUCCESS via principle-1's own
   downgrade is, by definition, only partially confirmed - so it reports
   PARTIAL_SUCCESS rather than UNKNOWN, distinct from "we have no signal
   either way" (see result_states.py's docstring on why those two are
   kept separate).

4. Fail closed.
   Every downgrade in this module only ever moves a state *away* from
   VERIFIED_SUCCESS (toward PARTIAL_SUCCESS) - it never upgrades a
   VERIFIED_FAILURE or UNKNOWN into something stronger, and it never
   touches read-only/query calls (see _READONLY_HINTS below), since
   demanding side-effect evidence from a call that has no side effect to
   evidence would just manufacture false negatives. When genuinely
   unsure whether a claim is earned, this module resolves that
   uncertainty toward the weaker claim, not the stronger one.

enforce() never raises - same "degrade, don't crash" stance as the rest
of this package; an internal failure returns the original outcome
unchanged rather than blocking verification.
"""

from __future__ import annotations

from .result_states import ResultState
from .verification_engine.base import VerifierOutcome

# Tools whose name signals "this only reads/reports, it doesn't change
# anything" - get_*, list_*, read_*, check_*, describe_*, find_* and
# similar. False-success protection's side-effect check does not apply to
# these: a query tool returning success=True with data already *is* its
# own evidence (the data is the answer), and one with no data at all
# (e.g. an empty list result) is a legitimate, truthful answer rather than
# a missing side effect.
_READONLY_PREFIXES = (
    "get_",
    "list_",
    "read_",
    "check_",
    "describe_",
    "find_",
    "search_",
    "recall_",
    "fact_check_",
    "identify_",
    "detect_",
    "is_",
    "has_",
)


def _looks_read_only(tool_name: str) -> bool:
    tool = (tool_name or "").lower()
    return tool.startswith(_READONLY_PREFIXES)


def enforce(evidence, outcome: VerifierOutcome) -> VerifierOutcome:
    """Apply the four principles above to one call's verifier outcome.
    `evidence` is a verification_engine.ToolEvidence-shaped object (see
    ../evidence_collector.py); `outcome` is what route_verifier()'s chosen
    domain verifier already decided. Returns outcome unchanged unless a
    principle above has a concrete reason to weaken it.

    Never raises - any unexpected shape in evidence/outcome degrades to
    returning outcome as-is rather than being the reason verify_turn()
    fails for the rest of the turn.
    """
    try:
        if outcome.state != ResultState.VERIFIED_SUCCESS:
            # Principle 4 (fail closed): nothing here ever strengthens a
            # FAILURE/PARTIAL/UNKNOWN outcome - only weakens a SUCCESS one.
            return outcome

        tool = evidence.tool_name

        # Principle 5 (source trust): learning/source_validator.py's verdict
        # on whatever this call cited, if evidence_collector.py found
        # anything to judge (see its _resolve_source_trust()). Applies even
        # to read-only/informational calls (a search result *is* the side
        # effect there) - a bare success=True backed only by a known
        # low-quality source isn't fully earned either, same fail-closed
        # spirit as principles 1-4, just with a source-trust source of
        # doubt instead of a missing-data one. Only ever weakens the
        # outcome, and only when the trust score itself is confidently low
        # (below the "unverified"/"neutral" default) - an unscored or
        # merely-neutral source is not itself grounds for a downgrade.
        source_trust = getattr(evidence, "source_trust", None)
        if source_trust is not None and source_trust < 0.35:
            downgraded_confidence = outcome.confidence
            try:
                from learning.confidence import score as _fact_confidence_score

                # Reuse the same extraction/source/corroboration weighting
                # learning/confidence.py uses for knowledge-base facts, so
                # a low-trust source erodes this call's confidence with the
                # same math a low-trust source erodes a fact's confidence.
                downgraded_confidence = _fact_confidence_score(
                    extraction_confidence=outcome.confidence,
                    source_trust=source_trust,
                    corroborating_sources=1,
                )
            except Exception:
                downgraded_confidence = min(outcome.confidence, 0.35)
            return VerifierOutcome(
                ResultState.PARTIAL_SUCCESS,
                f"{tool} reported success=True but its cited source scored a low trust_score "
                f"({source_trust:.2f}, tier={getattr(evidence, 'source_tier', None)}) via "
                "learning/source_validator.py - false-success protection fails this closed to "
                "PARTIAL_SUCCESS (see false_success_protection.py)",
                confidence=min(outcome.confidence, downgraded_confidence),
            )

        if _looks_read_only(tool):
            return outcome

        result = evidence.result
        if result.data:
            # There's at least some side-effect/result evidence for a
            # domain verifier to have already reasoned about - principle 2
            # is satisfied, nothing more for this generic layer to add.
            return outcome

        # Principle 1 + 2: a mutating action reported success=True with
        # absolutely no result data attached - no field a domain verifier
        # could have cross-checked against, and none for a person to
        # verify the claim against either. Fail closed (principle 3+4):
        # downgrade to PARTIAL_SUCCESS rather than letting the bare flag
        # stand as full confirmation.
        return VerifierOutcome(
            ResultState.PARTIAL_SUCCESS,
            f"{tool} reported success=True with no result data at all to confirm the side effect actually "
            "happened - false-success protection fails this closed to PARTIAL_SUCCESS (see "
            "false_success_protection.py)",
            confidence=min(outcome.confidence, 0.35),
        )
    except Exception:
        return outcome
