"""
Approval Rules (Phase 30 - Approval)
======================================
core/permissions.py's PermissionGate already knows *which tool names*
are destructive (a static DESTRUCTIVE_TOOLS set) but nothing about
*how* destructive, or whether context (autonomous vs. user-typed,
argument values like a target path) should change the answer. This
module adds that: a risk_level per action ("low" / "medium" / "high")
and a decide() call that action_manager.py/approval_manager.py use to
decide auto-allow vs. queue-for-approval, instead of the old binary
confirmed=True/False.

Deliberately reuses PermissionGate.DESTRUCTIVE_TOOLS as the seed for
"high" risk rather than duplicating the list - so a tool added there
is automatically "high" here too, no double bookkeeping.
"""

from typing import Dict, Optional

from core.permissions import PermissionGate

# Additional tools that aren't outright destructive (PermissionGate
# wouldn't flag them) but still touch things a user may want a say in -
# e.g. sending messages/emails on their behalf, spending money.
MEDIUM_RISK_TOOLS = {
    "send_email",
    "send_message",
    "send_whatsapp",
    "post_tweet",
    "make_purchase",
    "submit_form",
    "create_calendar_event",
}

# Source multiplier: an action requested by an autonomous loop
# (autonomy/task_loop-driven) is treated one risk tier higher than the
# same action typed directly by the user, since there's no human in
# the loop confirming intent at request time.
_RISK_ORDER = ["low", "medium", "high"]


class ApprovalRules:
    def __init__(self):
        self._gate = PermissionGate()

    def risk_level(self, action_name: str, source: str = "user") -> str:
        if action_name in self._gate.DESTRUCTIVE_TOOLS:
            base = "high"
        elif action_name in MEDIUM_RISK_TOOLS:
            base = "medium"
        else:
            base = "low"

        if source == "autonomous" and base != "high":
            idx = min(_RISK_ORDER.index(base) + 1, len(_RISK_ORDER) - 1)
            base = _RISK_ORDER[idx]

        return base

    def needs_approval(self, action_name: str, source: str = "user", arguments: Optional[Dict] = None) -> bool:
        """low -> auto-run, medium/high -> queue for approval, UNLESS the
        matching .env control-mode flag (core/control_mode.py) opts that
        whole category out of approval: ULTRON_SAFE_CONTROL for
        medium/low, ULTRON_UNSAFE_CONTROL for high (= destructive tools).
        `arguments` is accepted for future per-argument rules (e.g. a
        delete_file call scoped to a temp dir vs. system32) but isn't
        used yet - kept in the signature so callers don't need to
        change when that lands."""
        from core.control_mode import safe_control_enabled, unsafe_control_enabled

        level = self.risk_level(action_name, source)
        if level == "high":
            return not unsafe_control_enabled()
        if level == "medium":
            return not safe_control_enabled()
        return False


_instance: Optional[ApprovalRules] = None


def get_approval_rules() -> ApprovalRules:
    global _instance
    if _instance is None:
        _instance = ApprovalRules()
    return _instance
