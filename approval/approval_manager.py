"""
Approval Manager (Phase 30 - Approval)
=========================================
Single entry point for the approval/ package: given an action a
caller (execution/action_manager.py, autonomy/task_loop.py) wants to
run, decide whether it can go straight through or must wait for the
user, queue it via pending_actions.py if so, and notify the user it's
waiting.

This is the piece core/permissions.py's PermissionGate never had: a
place for the action to *wait*. PermissionGate still does the raw
tool-name check inside ActionPipeline (core/action_pipeline.py) for
the synchronous confirm=True/False case; ApprovalManager sits one
layer up and is what autonomy/task_loop.py and
execution/action_manager.py should call so a multi-step autonomous
run can pause on a single risky step without failing the whole run.

Notification: best-effort import of core.event_bus so a UI/voice
layer can surface "Ultron wants to <action> - approve?" without this
module needing to know how notifications are actually delivered.
"""

import threading
import time
from typing import Any, Dict, Optional

from core.logger import get_logger
from approval.approval_rules import get_approval_rules
from approval.pending_actions import get_pending_actions

logger = get_logger("ultron.approval_manager")


class ApprovalDecision:
    def __init__(self, allowed: bool, action_id: Optional[str] = None, risk_level: str = "low", reason: str = ""):
        self.allowed = allowed
        self.action_id = action_id
        self.risk_level = risk_level
        self.reason = reason

    def __repr__(self):
        return f"ApprovalDecision(allowed={self.allowed}, risk={self.risk_level}, action_id={self.action_id})"


class ApprovalManager:
    def __init__(self):
        self._rules = get_approval_rules()
        self._queue = get_pending_actions()

    def request(
        self, action_name: str, arguments: Optional[Dict[str, Any]] = None, source: str = "user", reason: str = ""
    ) -> ApprovalDecision:
        """Called before an action runs. Returns immediately - either
        allowed=True (safe to run now) or allowed=False with an
        action_id the caller should poll (or block on, via
        wait_for_decision) before proceeding."""
        arguments = arguments or {}
        risk = self._rules.risk_level(action_name, source)

        if not self._rules.needs_approval(action_name, source, arguments):
            return ApprovalDecision(allowed=True, risk_level=risk, reason="auto-approved (low risk)")

        action_id = self._queue.create(action_name, arguments, reason=reason, risk_level=risk)
        self._notify(action_name, action_id, risk)
        return ApprovalDecision(allowed=False, action_id=action_id, risk_level=risk, reason="waiting for user approval")

    def approve(self, action_id: str) -> bool:
        ok = self._queue.resolve(action_id, "approved")
        if ok:
            logger.info(f"Action {action_id} approved by user")
        return ok

    def deny(self, action_id: str) -> bool:
        ok = self._queue.resolve(action_id, "denied")
        if ok:
            logger.info(f"Action {action_id} denied by user")
        return ok

    def status(self, action_id: str) -> Optional[str]:
        row = self._queue.get(action_id)
        return row["status"] if row else None

    def wait_for_decision(self, action_id: str, timeout: float = 300.0, poll_interval: float = 1.0) -> str:
        """Blocking helper for synchronous callers (e.g. a workflow
        step that must know now). Returns final status
        ('approved'/'denied'/'expired'). Not used by anything that
        must stay responsive - task_loop.py should prefer the
        non-blocking request()+status() pair instead."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.status(action_id)
            if status and status != "pending":
                return status
            time.sleep(poll_interval)
        self._queue.resolve(action_id, "expired")
        return "expired"

    def pending(self):
        return self._queue.list_pending()

    def _notify(self, action_name: str, action_id: str, risk: str):
        try:
            from core.event_bus import get_event_bus

            get_event_bus().publish(
                "approval.requested",
                {
                    "action_id": action_id,
                    "action_name": action_name,
                    "risk_level": risk,
                },
            )
        except Exception as e:
            logger.debug(f"Could not publish approval.requested event: {e}")


_instance: Optional[ApprovalManager] = None
_instance_lock = threading.Lock()


def get_approval_manager() -> ApprovalManager:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ApprovalManager()
    return _instance
