"""
Automatic actions (Phase 25 - Proactive Automation)
======================================================
The last, most powerful, and most dangerous step of this phase's
pipeline: given a suggestion from proactive/suggester.py, decide
whether Ultron should just go ahead and do it instead of asking - and
if so, actually run it through core/action_pipeline.py.

Safe-by-default: nothing is auto-run unless ALL of the following hold,
checked in this order (cheapest/least-trust-requiring first):
  1. suggestion["auto_eligible"] is True (suggester.py already refused
     this for anything above "low" risk / below AUTO_ELIGIBLE_CONFIDENCE)
  2. the action_name is explicitly whitelisted via allow_action() - the
     whitelist starts EMPTY. Learning a pattern is not the same as
     being trusted to act on it unattended; a user opts specific
     actions in.
  3. proactive/disruption_guard.py says now is a clear moment (so
     automatic actions respect the exact same DND/quiet-hours/in-call
     rules as a spoken suggestion would - being silent doesn't exempt
     an action from "is this a bad time")
  4. a per-action cooldown hasn't already fired recently (so a
     borderline-confident pattern can't auto-fire every single tick)
  5. core/action_pipeline.py itself still re-checks permissions -
     confirmed=False is always passed, so even a whitelist misconfig
     can never auto-run anything core/permissions.py or
     capability_registry marks destructive/elevated; the pipeline's own
     gate is the final backstop, not this module's say-so.

Every actually-executed automatic action is (a) logged, (b) announced
via ui.notifications.notify() - Ultron never acts silently, even when
it decided not to ask first - and (c) emitted on core.event_bus as
"proactive.auto_action" so ui/ surfaces and predictor.py's own
"action.completed" subscription both see it like any other action.
"""

import threading
import time
from typing import Dict, Optional, Set

from proactive.disruption_guard import get_disruption_guard
from core.logger import get_logger

logger = get_logger("ultron.proactive.automatic_actions")

# Re-alerting/re-running the same automatic action too often would feel
# less like a helpful assistant and more like a misbehaving macro -
# once granted, still throttled.
ACTION_COOLDOWN_SECONDS = 20 * 60


class AutomaticActionExecutor:
    """Whitelist-gated, disruption-guard-gated, action_pipeline-executed
    "do it, don't just say it" path for eligible suggestions."""

    def __init__(self):
        self._guard = get_disruption_guard()
        self._whitelist: Set[str] = set()
        self._lock = threading.Lock()
        self._last_run: Dict[str, float] = {}

    # -- whitelist management -------------------------------------------------
    def allow_action(self, action_name: str) -> None:
        """Opt an action_name into automatic execution. Nothing runs
        unattended until this has been called for it at least once."""
        with self._lock:
            self._whitelist.add(action_name)
        logger.info(f"Automatic actions: '{action_name}' whitelisted.")

    def disallow_action(self, action_name: str) -> None:
        with self._lock:
            self._whitelist.discard(action_name)

    def is_allowed(self, action_name: str) -> bool:
        with self._lock:
            return action_name in self._whitelist

    def list_allowed(self) -> Set[str]:
        with self._lock:
            return set(self._whitelist)

    # -- execution -----------------------------------------------------------
    def consider(self, suggestion: Dict) -> Dict:
        """Given a suggester.py suggestion dict, either runs it and
        returns {"executed": True, "result": <action_pipeline result>}
        or declines and returns {"executed": False, "reason": ...} so the
        caller (proactive/engine.py) can fall back to just asking."""
        action_name = suggestion.get("action_name")

        if not suggestion.get("auto_eligible"):
            return self._skip(action_name, "not auto-eligible (risk or confidence too low)")

        if not self.is_allowed(action_name):
            return self._skip(action_name, "action not whitelisted for automatic execution")

        if self._in_cooldown(action_name):
            return self._skip(action_name, "action ran automatically too recently")

        if not self._guard.is_clear_to_interrupt("proactive_auto_action", urgency="normal"):
            return self._skip(action_name, "disruption guard held this back")

        return self._execute(action_name, suggestion)

    def _in_cooldown(self, action_name: str) -> bool:
        with self._lock:
            last = self._last_run.get(action_name)
        return last is not None and (time.time() - last) < ACTION_COOLDOWN_SECONDS

    def _execute(self, action_name: str, suggestion: Dict) -> Dict:
        from core.action_pipeline import get_action_pipeline

        pipeline = get_action_pipeline()
        arguments = suggestion.get("arguments") or {}
        # confirmed is always False here - an automatic action must never
        # be able to satisfy a destructive/elevated confirmation gate on
        # its own. See module docstring, safety step 5.
        result = pipeline.run(action_name, arguments=arguments, source="proactive_auto", confirmed=False)

        with self._lock:
            self._last_run[action_name] = time.time()

        if result.get("success"):
            self._announce(action_name, suggestion, result)
            logger.info(f"Automatic action '{action_name}' executed (confidence={suggestion.get('confidence')}).")
        else:
            logger.warning(f"Automatic action '{action_name}' failed: {result.get('error')}")

        self._emit(action_name, suggestion, result)
        return {"executed": bool(result.get("success")), "result": result}

    def _skip(self, action_name: str, reason: str) -> Dict:
        logger.debug(f"Automatic action '{action_name}' skipped: {reason}")
        return {"executed": False, "reason": reason}

    def _announce(self, action_name: str, suggestion: Dict, result: Dict) -> None:
        try:
            from ui.notifications import notify

            notify(
                title="Ultron",
                message=f"Went ahead and ran '{action_name}' for you, Sir - you usually do around now.",
                level="info",
                source="proactive.automatic_actions",
            )
        except Exception as e:
            logger.debug(f"Notification for automatic action unavailable: {e}")

    def _emit(self, action_name: str, suggestion: Dict, result: Dict) -> None:
        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit(
                "proactive.auto_action",
                action=action_name,
                success=bool(result.get("success")),
                confidence=suggestion.get("confidence"),
                basis=suggestion.get("basis"),
            )
        except Exception as e:
            logger.debug(f"Event bus emit for automatic action unavailable: {e}")


_executor: Optional[AutomaticActionExecutor] = None


def get_automatic_action_executor() -> AutomaticActionExecutor:
    global _executor
    if _executor is None:
        _executor = AutomaticActionExecutor()
    return _executor
