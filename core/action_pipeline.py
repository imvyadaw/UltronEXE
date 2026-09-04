"""
Action Pipeline (Phase 21 - Unified Core Architecture)
=======================================================
Before this, "run this action" meant a caller (main.py's tool-call
handling, autonomous_executor, a workflow step) each separately
checking permissions, calling core/executor.py's execute_tool, logging
the result into core/context.py, and telling core/error_handler.py
about failures - four call sites, four slightly different orders.
ActionPipeline is one funnel all of that goes through, in a fixed
order, so a new caller (autonomous_engine, in this same phase) gets
capability-check + permission-gate + confidence-tracking for free
instead of re-implementing it.

Fixed stages, always in this order:
  1. resolve   - does capability_registry know this action at all
  1.5 isolate  - security.capability_isolation's fine-grained scope
                 check (P1 - Capability Isolation). Orthogonal to
                 permission_level: a "normal" action can still be
                 denied here if its scope (filesystem_write, network,
                 shell_exec, communication_send, ...) is blocked or
                 ask-gated under the active isolation profile. Purely
                 additive - only ever adds a denial, never overrides
                 stage 2's decision.
  2. permit    - core.permissions.PermissionGate + the caller's
                 permission level (from user_manager, if a user_id was
                 given) - destructive actions need `confirmed=True`
  3. focus     - push onto consciousness so an interruption is visible
  4. execute   - capability's own handler if it registered one,
                 otherwise core.executor.execute_tool as the default
                 dispatcher (covers every LLM tool without each one
                 needing a duplicate capability_registry handler)
  5. record    - unified_context's conversation_context + consciousness
                 note_outcome() + event_bus "action.completed"/"action.failed"
                 + ai.tool_chain_optimizer's per-tool reliability stats
                 (P1 - Tool-Chain Optimizer), so ranking reflects every
                 action that actually ran, not just ones an LLM chose
                 to call.
  6. unfocus   - pop the focus pushed in step 3, always, even on failure
"""

import time
from typing import Any, Dict, Optional

from core.logger import get_logger
from core.error_handler import get_error_handler
from core.permissions import PermissionGate

logger = get_logger("ultron.action_pipeline")


class ActionPipeline:
    def __init__(self):
        self._gate = PermissionGate()
        self._error_handler = get_error_handler()

    def run(
        self,
        action_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        source: str = "user",
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        arguments = arguments or {}
        from core.capability_registry import get_capability_registry
        from core.consciousness import get_consciousness
        from core.unified_context import get_unified_context
        from core.event_bus import get_event_bus

        registry = get_capability_registry()
        registry.bootstrap()  # idempotent - same call ai.tool_runtime.execute_tool_from_dict
        # makes before its own registry.has() check. ActionPipeline.run() is
        # the other real caller (execution/action_manager.py, used by
        # core/orchestrator.py for every autonomous goal step) and was
        # missing this call entirely, so registry.get() below always hit an
        # empty table unless some *other* code path had already bootstrapped
        # it first in-process - every orchestrator-driven action failed with
        # "unknown or disabled capability" regardless of the tool name.
        consciousness = get_consciousness()
        context = get_unified_context()
        bus = get_event_bus()

        # 1. resolve
        capability = registry.get(action_name)
        if capability is None or not capability.enabled:
            result = self._fail(action_name, "unknown or disabled capability")
            bus.emit("action.failed", **result)
            return result

        # 1.5 isolate (P1 - Capability Isolation). For low/normal-risk
        # capabilities, a broken isolation module fails soft (logged,
        # not enforced) so one missing optional dependency doesn't take
        # down every action in the system. For destructive/elevated
        # capabilities this now fails CLOSED instead: a security
        # boundary that can't be checked must not silently become
        # optional for exactly the actions it exists to protect.
        is_high_risk = capability.permission_level in ("destructive", "elevated")
        try:
            from security.capability_isolation import get_capability_isolation

            iso_decision = get_capability_isolation().check(action_name, arguments)
            if not iso_decision["allowed"]:
                result = self._fail(
                    action_name,
                    iso_decision["reason"],
                    category="isolation_ask" if iso_decision["mode"] == "ask" else "isolation_denied",
                )
                bus.emit("action.blocked", **result)
                return result
        except Exception as e:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.action_pipeline.run")
            if is_high_risk:
                logger.error(
                    f"action_pipeline: capability isolation raised {type(e).__name__} "
                    f"while checking destructive/elevated action '{action_name}' - "
                    f"denying by default (fail-closed) rather than skipping the check."
                )
                result = self._fail(
                    action_name,
                    f"capability isolation unavailable ({type(e).__name__}) for a "
                    f"destructive/elevated action - denied by default",
                    category="isolation_denied",
                )
                bus.emit("action.blocked", **result)
                return result
            # Low/normal-risk action: isolation module unavailable, but
            # nothing here needed the extra scope check - proceed to the
            # normal permission gate below as before.

        # 2. permit
        if self._requires_confirmation(action_name, capability) and not confirmed:
            result = self._fail(action_name, "requires confirmation", category="needs_confirmation")
            bus.emit("action.blocked", **result)
            return result
        if not self._permitted_for_user(capability, user_id):
            result = self._fail(action_name, "insufficient permission level", category="permission_denied")
            bus.emit("action.blocked", **result)
            return result

        # 3. focus
        consciousness.push_focus(f"{action_name}({arguments})", source=source)
        started = time.time()
        try:
            # 4. execute
            if capability.handler:
                outcome = self._error_handler.run_safely(capability.handler, **arguments)
            else:
                # NOTE: this must be ai.tool_runtime.execute_tool_call, not
                # core.executor.execute_tool directly. execute_tool_call
                # checks _DIRECT_HANDLERS first (new_skills_tools.py,
                # movie_assistant_tools.py, apps_tools.py, browser_tools.py)
                # before falling back to core.executor - roughly half of
                # the current registered tools may be handled by _DIRECT_HANDLERS,
                # so calling core.executor.execute_tool here directly would
                # silently 404 them even though they work fine when called
                # the normal way. execute_tool_call returns a JSON string
                # (same convention as core.executor.execute_tool), which
                # run_safely already knows how to parse and error-check.
                from ai.tool_runtime import execute_tool_call

                outcome = self._error_handler.run_safely(execute_tool_call, action_name, arguments)

            success = bool(outcome.get("success", False))
            result = {
                "success": success,
                "action": action_name,
                "result": outcome.get("result"),
                "error": outcome.get("error"),
                "duration_seconds": round(time.time() - started, 2),
            }

            # 5. record
            context.conversation_context.record_tool_result(action_name, arguments, result)
            consciousness.note_outcome(success, detail=result.get("error") or "")
            bus.emit("action.completed" if success else "action.failed", **result)
            try:
                from ai.tool_chain_optimizer import get_tool_chain_optimizer

                get_tool_chain_optimizer().record_execution(
                    action_name,
                    success,
                    latency_ms=result.get("duration_seconds", 0) * 1000,
                    error=result.get("error"),
                )
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("core.action_pipeline.run")
            try:
                # P2 - Failure Pattern Learning Engine: same live-ingestion
                # point as the tool-chain optimizer above, kept as a
                # separate best-effort call so one failing to import/write
                # never blocks the other.
                from learning_engine.failure_pattern_engine import get_failure_pattern_engine

                get_failure_pattern_engine().record_outcome(action_name, success, error=result.get("error"))
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("core.action_pipeline.run")
            return result
        finally:
            # 6. unfocus
            consciousness.pop_focus()

    # -- helpers -----------------------------------------------------------
    def _requires_confirmation(self, action_name: str, capability) -> bool:
        return capability.permission_level == "destructive" or self._gate.requires_confirmation(action_name)

    def _permitted_for_user(self, capability, user_id: Optional[str]) -> bool:
        if capability.permission_level != "elevated" or not user_id:
            return capability.permission_level != "elevated"
        try:
            from core.user_manager import get_user_manager

            user = get_user_manager().get_user(user_id)
            return bool(user and user.get("permission_level") in ("elevated", "admin"))
        except Exception:
            return False

    def _fail(self, action_name: str, error: str, category: str = "unresolved") -> Dict[str, Any]:
        logger.warning(f"action_pipeline: '{action_name}' failed to run: {error}")
        return {"success": False, "action": action_name, "result": None, "error": error, "category": category}


_pipeline: Optional[ActionPipeline] = None


def get_action_pipeline() -> ActionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ActionPipeline()
    return _pipeline
