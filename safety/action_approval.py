"""
Action Approval (Phase 4.1 - Learning & Safety)
=================================================
Single entry point for "is Ultron allowed to run this action right
now, unattended?" - the module core/action_pipeline.py (or
core/autonomous_engine.py) should call before executing anything that
didn't come from a direct, just-now user command. Wraps
safety/trust_policy.py's classification with the two things a bare
trust level doesn't capture on its own:
  - explicit context overrides (e.g. "always confirm during a video
    call", checked via `context`)
  - routing AUTO_EXECUTE-eligible actions through safety/sandbox.py
    first, so "trusted" never means "runs for real with zero check"

Returns an ApprovalDecision, never executes anything itself and never
raises - callers get a decision object and act on it (execute directly,
run through sandbox first, or surface a confirmation prompt to the
user via core.permissions / core.action_pipeline's existing UI hook).
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from core.logger import get_logger
from safety.trust_policy import TrustLevel, get_trust_policy

logger = get_logger("ultron.safety.action_approval")


@dataclass
class ApprovalDecision:
    action_name: str
    trust_level: TrustLevel
    approved: bool
    requires_confirmation: bool
    run_in_sandbox: bool
    reason: str
    details: Dict = field(default_factory=dict)


class ActionApprovalGate:
    def __init__(self):
        self._lock = threading.Lock()
        # context flags that force ASK_EVERY_TIME regardless of trust,
        # e.g. {"in_call": True} set by voice_intelligence during a
        # live call - callers set these via force_ask_context()
        self._force_ask_context: Dict[str, bool] = {}

    def force_ask_context(self, flag: str, active: bool) -> None:
        with self._lock:
            self._force_ask_context[flag] = active

    def evaluate(self, action_name: str, context: Optional[Dict] = None) -> ApprovalDecision:
        context = context or {}
        with self._lock:
            active_force_flags = [f for f, v in self._force_ask_context.items() if v]

        if active_force_flags:
            return ApprovalDecision(
                action_name=action_name,
                trust_level=TrustLevel.ASK_EVERY_TIME,
                approved=False,
                requires_confirmation=True,
                run_in_sandbox=False,
                reason=f"context override active: {', '.join(active_force_flags)}",
            )

        trust_policy = get_trust_policy()
        level = trust_policy.get_trust_level(action_name)
        details = trust_policy.explain(action_name)

        if level == TrustLevel.ASK_EVERY_TIME:
            return ApprovalDecision(
                action_name=action_name,
                trust_level=level,
                approved=False,
                requires_confirmation=True,
                run_in_sandbox=False,
                reason="trust_policy: not enough confidence / destructive tool",
                details=details,
            )

        if level == TrustLevel.SUGGEST_ONLY:
            return ApprovalDecision(
                action_name=action_name,
                trust_level=level,
                approved=False,
                requires_confirmation=True,
                run_in_sandbox=False,
                reason="trust_policy: eligible to suggest, not to run unattended",
                details=details,
            )

        # AUTO_EXECUTE - approved, but still routed through sandbox.py
        # the first few times so "trusted" is verified live, not just
        # assumed from history. safety/sandbox.py's own SANDBOX_TRIAL_RUNS
        # decides how many more sandboxed runs remain for this action.
        from safety.sandbox import get_sandbox_executor

        needs_trial = get_sandbox_executor().needs_trial(action_name)
        return ApprovalDecision(
            action_name=action_name,
            trust_level=level,
            approved=True,
            requires_confirmation=False,
            run_in_sandbox=needs_trial,
            reason="trust_policy: auto-execute eligible" + (" (sandbox trial)" if needs_trial else ""),
            details=details,
        )


_gate: Optional[ActionApprovalGate] = None
_gate_lock = threading.Lock()


def get_action_approval_gate() -> ActionApprovalGate:
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = ActionApprovalGate()
        return _gate
