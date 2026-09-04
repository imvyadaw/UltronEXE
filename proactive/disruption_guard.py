"""
Disruption guard (Phase 25 - Proactive Automation)
====================================================
The "is right now actually an OK moment to say/do something" gate for
this phase's predictor.py -> suggester.py -> automatic_actions.py
pipeline. Deliberately does NOT reimplement DND/quiet-hours/cooldown
logic - intelligence/proactive_intelligence/user_disruption_guard.py
already owns that (with its own persisted settings + interruption log
in database/proactive_intelligence.db), and having two independent
do-not-disturb states in the same running assistant would be a bug,
not a feature: the user could turn DND on and still get interrupted by
whichever guard they didn't mean to configure.

So this module is a thin adapter, not a competing implementation:
  - evaluate()/check() delegate the actual allow/defer/suppress
    decision to intelligence.proactive_intelligence's shared guard.
  - what it adds is auto-filling the situational context that
    delegate.evaluate() needs (idle_seconds, in_call, fullscreen_active)
    from proactive/monitors/user_activity.py, so proactive/engine.py's
    tick loop doesn't need to gather that itself for every suggestion
    it wants to gate - it stays a one-line call.
  - set_dnd()/set_quiet_hours()/get_settings() are thin passthroughs so
    callers only need to import this one module.

Import of the shared guard is lazy (inside methods, not at module load)
to avoid a hard import-order dependency between the proactive/ and
intelligence/ packages at interpreter start-up - matches how
proactive/engine.py already lazy-imports things it only needs at call
time in a couple of spots.
"""

from typing import Dict, Optional, Set

from proactive.monitors.user_activity import get_user_activity_monitor
from core.logger import get_logger

logger = get_logger("ultron.proactive.disruption_guard")

# Active-window substrings (case-insensitive) treated as "user is
# probably in a call" - same idea as triggers/event_driven.py's
# INTERESTING_APPS, scoped to this narrower purpose.
CALL_APP_HINTS: Set[str] = {"zoom", "teams", "google meet", "meet.google", "skype"}
# Active-window substrings treated as "probably fullscreen video/game/
# presentation" - best-effort heuristic (no real fullscreen API check
# here), good enough to hold back a low-urgency nudge.
FULLSCREEN_APP_HINTS: Set[str] = {"powerpoint slide show", "netflix", "youtube - ", "steam"}

DECISION_ALLOW = "allow"
DECISION_DEFER = "defer"
DECISION_SUPPRESS = "suppress"
URGENCY_CRITICAL = "critical"


class ProactiveDisruptionGuard:
    """Context-auto-filling adapter in front of the shared, persisted
    UserDisruptionGuard. See module docstring."""

    def __init__(self):
        self._activity = get_user_activity_monitor()

    def _shared_guard(self):
        from intelligence.proactive_intelligence.user_disruption_guard import get_user_disruption_guard

        return get_user_disruption_guard()

    def _auto_context(self, extra: Optional[Dict] = None) -> Dict:
        snapshot = self._activity.snapshot()
        window = (snapshot.get("active_window") or "").lower()
        context = {
            "idle_seconds": snapshot.get("idle_seconds") or 0,
            "in_call": any(hint in window for hint in CALL_APP_HINTS),
            "fullscreen_active": any(hint in window for hint in FULLSCREEN_APP_HINTS),
        }
        if extra:
            context.update({k: v for k, v in extra.items() if v is not None})
        return context

    def check(
        self, category: str, event_type: str = "proactive", urgency: str = "normal", context: Optional[Dict] = None
    ) -> Dict:
        """Returns {"decision": allow/defer/suppress, "reason", "defer_until",
        "reasons"} - same shape as the shared guard's evaluate(), with
        context auto-filled from live monitors unless the caller already
        supplied some/all of it (explicit values always win)."""
        try:
            guard = self._shared_guard()
        except Exception as e:
            logger.debug(f"Shared disruption guard unavailable, defaulting to allow: {e}")
            return {"decision": DECISION_ALLOW, "reason": "guard unavailable", "defer_until": None, "reasons": []}

        full_context = self._auto_context(context)
        event = {"event_type": event_type, "category": category}
        try:
            return guard.evaluate(event, urgency, full_context)
        except Exception as e:
            logger.error(f"Disruption guard evaluate() failed, defaulting to allow: {e}")
            return {"decision": DECISION_ALLOW, "reason": "guard error", "defer_until": None, "reasons": []}

    def is_clear_to_interrupt(self, category: str, urgency: str = "normal", context: Optional[Dict] = None) -> bool:
        """Convenience boolean for call sites that just need a yes/no
        (e.g. automatic_actions.py deciding whether to act now)."""
        return self.check(category, urgency=urgency, context=context)["decision"] == DECISION_ALLOW

    # -- passthrough settings ------------------------------------------------
    def set_dnd(self, enabled: bool, minutes: Optional[float] = None, allow_critical: Optional[bool] = None) -> Dict:
        return self._shared_guard().set_dnd(enabled, minutes=minutes, allow_critical=allow_critical)

    def set_quiet_hours(
        self, start_hour: int, start_minute: int, end_hour: int, end_minute: int, enabled: bool = True
    ) -> Dict:
        return self._shared_guard().set_quiet_hours(start_hour, start_minute, end_hour, end_minute, enabled=enabled)

    def get_settings(self) -> Dict:
        return self._shared_guard().get_settings()


_guard: Optional[ProactiveDisruptionGuard] = None


def get_disruption_guard() -> ProactiveDisruptionGuard:
    global _guard
    if _guard is None:
        _guard = ProactiveDisruptionGuard()
    return _guard
