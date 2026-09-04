"""
Learning Policy (Phase 4.1 - Learning & Safety)
=================================================
The gate learning/learner.py checks before letting an observed outcome
move a trust number. Two separate questions live here, deliberately
kept apart:
  - is_action_learnable()  - should this action's outcomes be folded
                              into confidence at all? (privacy/safety
                              exclusions, e.g. never auto-learn from
                              destructive actions no matter how many
                              times they "succeed")
  - min_confidence_required() - even when an action IS learnable, how
                              sure does the learner need to be before
                              safety/trust_policy.py is allowed to treat
                              it as trustworthy?

This is intentionally the only module with an EXCLUDED_ACTIONS list -
core.permissions.PermissionGate.DESTRUCTIVE_TOOLS decides whether a
single run needs a confirmation prompt; this decides whether repeated
runs are even allowed to *earn* the right to skip that prompt someday.
Every entry in PermissionGate.DESTRUCTIVE_TOOLS is excluded here by
default for that reason - being asked for confirmation every time is
the whole point of "destructive", it shouldn't be something a good
streak quietly erodes.
"""

import threading
from typing import Dict, Optional, Set

from core.logger import get_logger

logger = get_logger("ultron.safety.learning_policy")

# actions that must never have their outcomes folded into a trust
# score, regardless of how many times they've "succeeded" - still
# logged by learning/experience.py for audit, just never counted
DEFAULT_EXCLUDED_ACTIONS: Set[str] = {
    "shutdown_pc",
    "restart_pc",
    "sign_out",
    "delete_file",
    "delete_folder",
    "kill_process",
    "stop_service",
    "remove_rule",
    "remove_startup_program",
    "delete_value",
    "clear_downloads",
    "run_command",
    "run_powershell",
    "call_phone",
    "relaunch_as_admin",
}

# per-action override of how many *learnable* observations are needed
# before trust_policy is allowed to call an action "confident" - unset
# actions fall back to DEFAULT_MIN_SAMPLES
SENSITIVE_MIN_SAMPLES: Dict[str, int] = {
    "send_email": 15,
    "send_message": 15,
    "post_to_social": 20,
    "make_payment": 999999,  # effectively "never learn your way to auto-trust"
}

DEFAULT_MIN_SAMPLES = 5


class LearningPolicy:
    def __init__(self, excluded: Optional[Set[str]] = None):
        self._lock = threading.Lock()
        self._excluded = set(excluded) if excluded is not None else set(DEFAULT_EXCLUDED_ACTIONS)
        self._sensitive_min_samples = dict(SENSITIVE_MIN_SAMPLES)

    def is_action_learnable(self, action_name: str) -> bool:
        with self._lock:
            return action_name not in self._excluded

    def min_confidence_samples(self, action_name: str) -> int:
        with self._lock:
            return self._sensitive_min_samples.get(action_name, DEFAULT_MIN_SAMPLES)

    def exclude_action(self, action_name: str, reason: str = "") -> None:
        with self._lock:
            self._excluded.add(action_name)
        logger.info(f"learning_policy: excluded '{action_name}' from learning ({reason or 'no reason given'})")

    def include_action(self, action_name: str) -> None:
        """Explicit opt-back-in. Deliberately does not touch the
        DEFAULT_EXCLUDED_ACTIONS set's intent silently - a caller
        removing a genuinely destructive tool from exclusion should
        know that's what it's doing."""
        with self._lock:
            self._excluded.discard(action_name)
        logger.warning(f"learning_policy: '{action_name}' re-included in learning")

    def excluded_actions(self) -> Set[str]:
        with self._lock:
            return set(self._excluded)


_policy: Optional[LearningPolicy] = None
_policy_lock = threading.Lock()


def get_learning_policy() -> LearningPolicy:
    global _policy
    with _policy_lock:
        if _policy is None:
            _policy = LearningPolicy()
        return _policy
