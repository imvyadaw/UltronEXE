"""
Result normalizer
==================
Turns whatever core/executor.py + ai/tool_runtime.py handed back for one
tool call - a JSON string, an already-parsed dict, or anything else - into
one predictable shape (`NormalizedResult`) the rest of the hardening layer
(evidence collector, verifiers, truth gate) can rely on without each of
them re-implementing "is this dict-shaped, is 'success' even present"
parsing.

Every newer tool in this codebase already tries to return
`{"success": bool, ...}` or `{"error": "..."}` (see ai/tool_runtime.py's
_DIRECT_HANDLERS and most of core/executor.py's tool_map), but that
convention was never enforced, and a chunk of core/executor.py's older
tool_map lambdas just return whatever the underlying windows/ call
returned - could be a plain string, a list, a bare dict with neither key.
This module is the one place that reconciles those inconsistent shapes.
Never raises - same "degrade, don't crash" pattern as the rest of
Phase 29/29-A.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class NormalizedResult:
    tool_name: str
    success: Optional[bool]  # True/False when the tool told us either way, None when it didn't
    error: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def is_error(self) -> bool:
        return self.success is False or bool(self.error)


def _coerce_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except (TypeError, ValueError):
            return {"text": raw}
    if isinstance(raw, (list, tuple)):
        return {"value": list(raw)}
    return {"value": raw}


def normalize(tool_name: str, raw_result: Any) -> NormalizedResult:
    """Never raises. A result that can't be reconciled at all comes back as
    NormalizedResult(success=None, error=<why>, data={}) rather than
    propagating an exception into the verification engine."""
    try:
        d = _coerce_dict(raw_result)
    except Exception as e:  # pragma: no cover - _coerce_dict shouldn't raise; belt+braces
        return NormalizedResult(tool_name=tool_name, success=None, error=f"normalize failed: {e}", raw=raw_result)

    error = d.get("error")

    if "success" in d:
        success: Optional[bool] = bool(d.get("success"))
    elif error:
        success = False
    elif (tool_name or "").lower().startswith("unknown tool"):
        success = False
    else:
        # No explicit success/error signal either way. A fair chunk of
        # core/executor.py's older tool_map lambdas are like this - they
        # just forward whatever windows/ returned. Leaving this as None
        # (rather than guessing True) is deliberate: it's exactly the
        # ambiguity verification_engine's verifiers are there to resolve
        # per tool-category, or fall through to UNKNOWN if they can't.
        success = None

    data = {k: v for k, v in d.items() if k not in ("success", "error")}
    return NormalizedResult(
        tool_name=tool_name,
        success=success,
        error=str(error) if error else None,
        data=data,
        raw=raw_result,
    )
