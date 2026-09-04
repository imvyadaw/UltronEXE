"""
Phase 29-B - Result hardening & verification layer
====================================================
Sits on top of the existing tool-calling runtime (AI Router -> Tool
Selector -> Tool Runtime -> Executor) and alongside Phase 29-A's stability
layer. Where 29-A made sure a tool call *can* run without crashing the app
and added a first, lightweight regex-based truth check
(truth_prompt_contract.check_turn()), 29-B is the deeper pipeline that
actually classifies what each tool call's result means:

    Result Normalizer -> Evidence Collector -> Verification Engine
        (+ False-Success Protection) -> Truth Gate -> Response Truth Guard

See README.md for the full picture and result_states.py for the four
result states (VERIFIED_SUCCESS / VERIFIED_FAILURE / PARTIAL_SUCCESS /
UNKNOWN) every tool call ends up classified into. The verification engine
routes each call to one of ten domain verifiers (System / App / Browser /
File / Keyboard-Mouse / Media / Voice-TTS / Memory / Automation /
Integration - see verification_engine/verifiers.py), then
false_success_protection.py's enforce() applies four cross-cutting
never-trust-a-bare-flag principles on top before truth_gate.py compares
the result against the response text and classifies the turn into a
strict claim policy (see truth_gate.py's CLAIM_POLICY).

Public surface - everything else in this package is an implementation
detail callers shouldn't need to import directly.
"""

from .evidence_collector import ToolEvidence, TurnEvidence, build_turn_evidence
from .false_success_protection import enforce as enforce_false_success_protection
from .response_truth_guard import TurnHardeningReport, guard_turn
from .result_normalizer import NormalizedResult, normalize
from .result_states import ResultState, combine
from .truth_gate import CLAIM_POLICY, TruthGateVerdict
from .truth_gate import claim_policy
from .truth_gate import evaluate as evaluate_truth_gate
from .verification_engine import CallVerification, TurnVerification, verify_turn

__all__ = [
    "ResultState",
    "combine",
    "NormalizedResult",
    "normalize",
    "ToolEvidence",
    "TurnEvidence",
    "build_turn_evidence",
    "CallVerification",
    "TurnVerification",
    "verify_turn",
    "enforce_false_success_protection",
    "TruthGateVerdict",
    "evaluate_truth_gate",
    "CLAIM_POLICY",
    "claim_policy",
    "TurnHardeningReport",
    "guard_turn",
]
