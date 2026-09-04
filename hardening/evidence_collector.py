"""
Evidence collector
===================
Groups one turn's tool calls (name + arguments + normalized result, in
call order) into a single `TurnEvidence` object. This is the only object
the verification engine and truth gate consume - neither of them touches
raw tool-runtime output directly.

Deliberately dumb: no verification logic lives here, just assembly. That
keeps "what counts as verified" (verification_engine/) separate from
"what happened this turn" (this module) - the same separation-of-concerns
Phase 29-A used for lazy_loader.py (mechanism) vs dependency_validator.py
(policy).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .result_normalizer import NormalizedResult, normalize

# Keys a tool result might carry its source/citation under - checked in
# order, first match wins. Kept narrow and literal (no guessing at nested
# shapes) since this only feeds an advisory trust score, never a hard gate.
_SOURCE_KEYS = ("source", "url", "sources", "urls", "citation", "citations")


@dataclass
class ToolEvidence:
    tool_name: str
    arguments: Dict[str, Any]
    result: NormalizedResult
    timestamp: float = field(default_factory=time.time)
    # Best-effort trust verdict for whatever source(s) this call's result
    # cites, via learning/source_validator.py - None when the result carried
    # no source/url to judge (most tool calls) or the validator itself
    # isn't available. Populated by _resolve_source_trust() below; consumed
    # by false_success_protection.py (weak claim -> PARTIAL_SUCCESS) and
    # truth_gate.py (weak claim -> its own mismatch note), so a call that
    # merely *looks* successful but leans on a low-quality source doesn't
    # sail through as a full VERIFIED_SUCCESS.
    source_trust: Optional[float] = None
    source_tier: Optional[str] = None


@dataclass
class TurnEvidence:
    calls: List[ToolEvidence] = field(default_factory=list)

    @property
    def has_calls(self) -> bool:
        return bool(self.calls)


def _resolve_source_trust(tool_name: str, raw_result: Any):
    """Best-effort: if raw_result carries something that looks like a
    cited source/url, score it via learning/source_validator.py's
    SourceValidator. Returns (trust_score, tier) or (None, None) - never
    raises, and a missing/broken source_validator (or a result with no
    source-shaped field at all) just means this call gets no trust
    signal, same as every call did before this hook existed."""
    if not isinstance(raw_result, dict):
        return None, None
    source_value = None
    for key in _SOURCE_KEYS:
        if raw_result.get(key):
            source_value = raw_result[key]
            break
    if not source_value:
        return None, None
    # A list of sources (e.g. several search results) - judge the first,
    # since that's the one most likely to have actually backed the claim.
    if isinstance(source_value, (list, tuple)):
        source_value = source_value[0] if source_value else None
    if isinstance(source_value, dict):
        source_value = source_value.get("url") or source_value.get("name")
    if not isinstance(source_value, str):
        return None, None
    try:
        from learning.source_validator import SourceValidator

        validator = SourceValidator()
        verdict = validator.validate(name=source_value, url=source_value)
        if isinstance(verdict, dict) and "error" not in verdict:
            return verdict.get("trust_score"), verdict.get("tier")
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("hardening.evidence_collector._resolve_source_trust")
    return None, None


def build_turn_evidence(tool_calls: Optional[List[Dict[str, Any]]]) -> TurnEvidence:
    """tool_calls: list of {"tool_name": str, "arguments": dict, "raw_result": Any}
    in the order they were executed this turn (matches how
    ai/cloud_models/groq_client.py's chat_with_tools() already tracks a
    turn's tool calls). Never raises - a malformed entry is skipped rather
    than aborting evidence collection for the whole turn, so one bad entry
    can't blind the truth gate to every other call this turn made."""
    evidence = TurnEvidence()
    for entry in tool_calls or []:
        try:
            tool_name = entry.get("tool_name") or "unknown"
            arguments = entry.get("arguments") or {}
            raw_result = entry.get("raw_result")
            normalized = normalize(tool_name, raw_result)
            trust, tier = _resolve_source_trust(tool_name, raw_result)
            evidence.calls.append(
                ToolEvidence(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=normalized,
                    source_trust=trust,
                    source_tier=tier,
                )
            )
        except Exception:
            continue
    return evidence
