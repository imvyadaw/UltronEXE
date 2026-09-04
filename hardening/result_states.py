"""
Result states
=============
The four states every tool call - and every turn as a whole - gets
classified into by the verification engine (see verification_engine/):

    VERIFIED_SUCCESS  - a verifier positively confirmed the action happened
                         as claimed (explicit success signal, and where a
                         verifier has domain-specific checks, those passed
                         too).
    VERIFIED_FAILURE  - the tool reported an error, or a verifier's
                         domain-specific check positively contradicts
                         success (e.g. a confirm-gated destructive action
                         that never actually ran).
    PARTIAL_SUCCESS   - something happened, but not everything the call
                         implied (a chained action's first step worked and
                         a later one didn't; a result came back with no
                         explicit success/error signal but has plausible
                         data attached).
    UNKNOWN           - not enough signal either way to classify. This is
                         the default for anything a verifier can't reason
                         about, deliberately distinct from VERIFIED_FAILURE -
                         "we can't confirm this" is not the same claim as
                         "we confirmed this didn't happen".
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class ResultState(str, Enum):
    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    UNKNOWN = "UNKNOWN"


# Used only as a last-resort tiebreak inside combine() below - not a claim
# that one state is "worse" than another in isolation, just an ordering so
# combine() has a deterministic answer for state-sets it has no explicit
# rule for.
_PRIORITY = {
    ResultState.VERIFIED_FAILURE: 3,
    ResultState.PARTIAL_SUCCESS: 2,
    ResultState.UNKNOWN: 1,
    ResultState.VERIFIED_SUCCESS: 0,
}


def combine(states: Iterable[ResultState]) -> ResultState:
    """Combine several per-call states into one turn-level state.

    - No calls at all -> UNKNOWN (nothing to verify against; this is what
      a pure-conversation turn with no tool calls looks like, and it
      should never be reported as a failure).
    - Every call VERIFIED_SUCCESS -> VERIFIED_SUCCESS.
    - Every call VERIFIED_FAILURE -> VERIFIED_FAILURE.
    - A mix that includes at least one VERIFIED_SUCCESS alongside any
      VERIFIED_FAILURE or PARTIAL_SUCCESS -> PARTIAL_SUCCESS (some of a
      multi-step turn worked, some didn't - the "partial" case a blanket
      done/failed report would hide, per TRUTH_CONTRACT_ADDENDUM's
      multi-step-chain rule).
    - A mix of VERIFIED_SUCCESS and only UNKNOWN -> PARTIAL_SUCCESS too;
      treated conservatively rather than let confirmed successes mask an
      unverifiable call.
    - Anything else falls back to the highest-priority state present.
    """
    states = list(states)
    if not states:
        return ResultState.UNKNOWN

    uniq = set(states)
    if uniq == {ResultState.VERIFIED_SUCCESS}:
        return ResultState.VERIFIED_SUCCESS
    if uniq == {ResultState.VERIFIED_FAILURE}:
        return ResultState.VERIFIED_FAILURE
    if uniq == {ResultState.UNKNOWN}:
        return ResultState.UNKNOWN
    if ResultState.VERIFIED_SUCCESS in uniq and len(uniq) > 1:
        return ResultState.PARTIAL_SUCCESS
    return max(uniq, key=lambda s: _PRIORITY[s])
