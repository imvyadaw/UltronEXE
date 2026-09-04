"""
Verifier base classes
======================
One verifier per tool-category (System / App / Browser / File /
Keyboard-Mouse / Media / Voice-TTS / Memory / Automation / Integration -
see verifiers.py). Every verifier answers one
question for one tool call: given what the tool actually returned, what
ResultState does this call deserve?
"""

from __future__ import annotations

from dataclasses import dataclass

from ..result_states import ResultState


@dataclass
class VerifierOutcome:
    state: ResultState
    reason: str
    # 0-1, best-effort self-reported confidence. Not currently used to gate
    # anything (the truth gate treats every VerifierOutcome the same
    # regardless of confidence) - kept so a future tiering/logging pass has
    # somewhere to read it from without another schema change.
    confidence: float = 0.5


class BaseVerifier:
    """verify() must never raise. verification_engine/__init__.py's
    verify_turn() wraps every call in a try/except that degrades to
    UNKNOWN on an unexpected exception, but individual verifiers should
    still handle their own expected edge cases (missing keys, wrong types)
    directly rather than relying on that outer safety net."""

    name = "base"

    def verify(self, evidence) -> VerifierOutcome:  # evidence: ToolEvidence
        raise NotImplementedError
