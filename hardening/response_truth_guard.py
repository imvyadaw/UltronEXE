"""
Response truth guard
=====================
The single entry point the rest of the app - currently
ai/cloud_models/groq_client.py's chat_with_tools(), and any future AI
backend that wants the same coverage - calls at the end of a turn. Runs
the full Phase 29-B pipeline:

    Result Normalizer -> Evidence Collector -> Verification Engine
        -> Truth Gate

and returns one TurnHardeningReport.

Deliberately advisory only, same stance as
stability.truth_prompt_contract.check_turn(): logs a warning
when the gate flags something, never rewrites or withholds the response. A
hardening layer that could silently alter what the user is told is a
bigger risk than the problem it's meant to catch. guard_turn() itself
never raises - any failure inside the pipeline degrades to an UNKNOWN/ok
report rather than being the reason a real response fails to return.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from core.logger import get_logger

    _logger = get_logger("ultron.stability.response_truth_guard")
except Exception:  # pragma: no cover - logger itself should never be why this module fails to import
    import logging

    _logger = logging.getLogger("ultron.stability.response_truth_guard")

from stability.truth_prompt_contract import TruthCheckResult

from .evidence_collector import build_turn_evidence
from .result_states import ResultState
from .truth_gate import TruthGateVerdict, evaluate as evaluate_truth_gate
from .verification_engine import verify_turn


@dataclass
class TurnHardeningReport:
    turn_state: ResultState
    verdict: TruthGateVerdict

    @property
    def ok(self) -> bool:
        return self.verdict.ok

    def summary(self) -> str:
        return self.verdict.summary()


def guard_turn(
    response_text: str,
    tool_names: Optional[List[str]] = None,
    tool_args: Optional[List[Dict[str, Any]]] = None,
    tool_results: Optional[List[Any]] = None,
) -> TurnHardeningReport:
    """tool_names / tool_args / tool_results are three parallel lists -
    index i across all three describes one tool call, in the order it ran
    this turn. tool_results entries may be JSON strings or already-parsed
    dicts; either is fine, result_normalizer.normalize() handles both.

    Never raises: any exception anywhere in the pipeline is caught and
    logged, and a conservative ok=True/UNKNOWN report is returned instead -
    a hardening layer must never be the reason a real response fails to
    return.
    """
    try:
        tool_names = tool_names or []
        tool_args = tool_args or []
        tool_results = tool_results or []
        n = max(len(tool_names), len(tool_args), len(tool_results))

        calls = [
            {
                "tool_name": tool_names[i] if i < len(tool_names) else "unknown",
                "arguments": tool_args[i] if i < len(tool_args) else {},
                "raw_result": tool_results[i] if i < len(tool_results) else None,
            }
            for i in range(n)
        ]

        evidence = build_turn_evidence(calls)
        verification = verify_turn(evidence)
        verdict = evaluate_truth_gate(response_text, evidence, verification)

        report = TurnHardeningReport(turn_state=verification.turn_state, verdict=verdict)
        if not report.ok:
            _logger.warning(report.summary())
        return report
    except Exception as e:  # pragma: no cover - belt+braces, see module docstring
        try:
            _logger.warning(f"response_truth_guard.guard_turn failed internally, degrading to UNKNOWN/ok: {e}")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("hardening.response_truth_guard.guard_turn")
        return TurnHardeningReport(
            turn_state=ResultState.UNKNOWN,
            verdict=TruthGateVerdict(ok=True, turn_state=ResultState.UNKNOWN, regex_check=TruthCheckResult(ok=True)),
        )
