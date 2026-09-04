"""
Verification engine
====================
verify_turn(evidence) runs every tool call in a TurnEvidence (see
../evidence_collector.py) through the right domain verifier (see
verifiers.py's route_verifier()) and combines the per-call ResultStates
into one turn-level ResultState (see ../result_states.py's combine()).

A verifier raising is never fatal to the rest of the turn's verification -
each call is wrapped independently and degrades to UNKNOWN on failure, the
same "one bad entry can't blind the whole turn" stance evidence_collector.py
takes for a malformed tool-call entry.

After a domain verifier decides a call's outcome, verify_turn() also runs
it through ../false_success_protection.py's enforce() - a cross-cutting,
tool-agnostic check (never trust success=True alone, fail closed on
missing side-effect evidence) that applies on top of, not instead of, the
domain-specific reasoning above.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..evidence_collector import ToolEvidence, TurnEvidence
from ..result_states import ResultState, combine
from .base import VerifierOutcome
from .verifiers import route_verifier

__all__ = ["CallVerification", "TurnVerification", "verify_turn", "VerifierOutcome"]


@dataclass
class CallVerification:
    evidence: ToolEvidence
    outcome: VerifierOutcome
    verifier_name: str


@dataclass
class TurnVerification:
    calls: List[CallVerification] = field(default_factory=list)
    turn_state: ResultState = ResultState.UNKNOWN

    def summary(self) -> str:
        if not self.calls:
            return "verification: no tool calls this turn"
        lines = [f"verification: turn_state={self.turn_state.value}"]
        for c in self.calls:
            lines.append(
                f"  [{c.outcome.state.value}] {c.evidence.tool_name} (via {c.verifier_name} verifier): {c.outcome.reason}"
            )
        return "\n".join(lines)


def verify_turn(evidence: TurnEvidence) -> TurnVerification:
    # Local import - false_success_protection.py imports .base (this
    # package), so importing it at module load time would be circular.
    from ..false_success_protection import enforce as enforce_false_success_protection

    result = TurnVerification()
    for call in evidence.calls:
        verifier = route_verifier(call.tool_name)
        try:
            outcome = verifier.verify(call)
        except Exception as e:
            outcome = VerifierOutcome(
                ResultState.UNKNOWN, f"verifier raised ({e}) - degraded to UNKNOWN", confidence=0.0
            )
        try:
            outcome = enforce_false_success_protection(call, outcome)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("hardening.verification_engine.__init__.verify_turn")
        result.calls.append(CallVerification(evidence=call, outcome=outcome, verifier_name=verifier.name))
    result.turn_state = combine(c.outcome.state for c in result.calls)
    return result
