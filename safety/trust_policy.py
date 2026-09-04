"""
Trust Policy (Phase 4.1 - Learning & Safety)
==============================================
Turns learning/learner.py's confidence number into a decision Ultron
can actually act on: for a given action, is it ASK_EVERY_TIME,
SUGGEST_ONLY, or AUTO_EXECUTE? safety/action_approval.py is the normal
caller - this module only classifies, it never runs anything and never
talks to event_bus directly.

Three inputs decide the trust level, in this order:
  1. core.permissions.PermissionGate - if the tool is in
     DESTRUCTIVE_TOOLS, trust level is capped at ASK_EVERY_TIME. No
     amount of learned confidence overrides this; that's the whole
     contract PermissionGate exists to guarantee.
  2. safety.learning_policy - if the action isn't learnable, or hasn't
     cleared its required sample size yet, trust level is capped at
     SUGGEST_ONLY (Ultron can propose it, not do it unasked).
  3. learning.learner's confidence score - only once the above two
     don't block it does the actual number decide ASK vs SUGGEST vs
     AUTO.
"""

import threading
from enum import Enum
from typing import Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.safety.trust_policy")

# confidence >= this -> AUTO_EXECUTE eligible (still subject to the
# PermissionGate/learning_policy caps above)
AUTO_EXECUTE_THRESHOLD = 0.85
# confidence >= this (but below AUTO_EXECUTE_THRESHOLD) -> SUGGEST_ONLY
SUGGEST_THRESHOLD = 0.55


class TrustLevel(str, Enum):
    ASK_EVERY_TIME = "ask_every_time"
    SUGGEST_ONLY = "suggest_only"
    AUTO_EXECUTE = "auto_execute"


class TrustPolicy:
    def __init__(self):
        self._lock = threading.Lock()
        # per-action manual pins, e.g. an admin forcing an action to
        # always ask regardless of what the numbers say - checked before
        # anything else
        self._pinned: Dict[str, TrustLevel] = {}

    def pin(self, action_name: str, level: TrustLevel) -> None:
        with self._lock:
            self._pinned[action_name] = level
        logger.info(f"trust_policy: pinned '{action_name}' to {level.value}")

    def unpin(self, action_name: str) -> None:
        with self._lock:
            self._pinned.pop(action_name, None)

    def get_trust_level(self, action_name: str) -> TrustLevel:
        with self._lock:
            pinned = self._pinned.get(action_name)
        if pinned is not None:
            return pinned

        from core.control_mode import safe_control_enabled, unsafe_control_enabled
        from core.permissions import PermissionGate

        if PermissionGate().requires_confirmation(action_name):
            # ULTRON_UNSAFE_CONTROL=true in .env: user has explicitly opted
            # this whole "destructive tools" category into running
            # unattended - overrides the normal ASK_EVERY_TIME cap.
            if unsafe_control_enabled():
                return TrustLevel.AUTO_EXECUTE
            return TrustLevel.ASK_EVERY_TIME

        # ULTRON_SAFE_CONTROL=true: skip the learned-confidence ramp-up
        # below entirely for anything that isn't a destructive tool.
        if safe_control_enabled():
            return TrustLevel.AUTO_EXECUTE

        from safety.learning_policy import get_learning_policy

        policy = get_learning_policy()
        if not policy.is_action_learnable(action_name):
            return TrustLevel.SUGGEST_ONLY

        from learning.learner import get_learner

        learner = get_learner()
        stats = learner.get_stats(action_name)
        required = policy.min_confidence_samples(action_name)
        if stats["sample_size"] < required:
            return TrustLevel.SUGGEST_ONLY

        confidence = learner.get_confidence(action_name)
        if confidence is None:
            return TrustLevel.SUGGEST_ONLY
        if confidence >= AUTO_EXECUTE_THRESHOLD:
            return TrustLevel.AUTO_EXECUTE
        if confidence >= SUGGEST_THRESHOLD:
            return TrustLevel.SUGGEST_ONLY
        return TrustLevel.ASK_EVERY_TIME

    def explain(self, action_name: str) -> Dict:
        """Same decision as get_trust_level(), but with the numbers
        that produced it - for a debug console or a user asking
        'why did/didn't you just do that yourself'."""
        from learning.learner import get_learner
        from safety.learning_policy import get_learning_policy

        level = self.get_trust_level(action_name)
        stats = get_learner().get_stats(action_name)
        confidence = get_learner().get_confidence(action_name)
        return {
            "action_name": action_name,
            "trust_level": level.value,
            "confidence": confidence,
            "sample_size": stats["sample_size"],
            "required_samples": get_learning_policy().min_confidence_samples(action_name),
            "learnable": get_learning_policy().is_action_learnable(action_name),
        }


_trust_policy: Optional[TrustPolicy] = None
_trust_policy_lock = threading.Lock()


def get_trust_policy() -> TrustPolicy:
    global _trust_policy
    with _trust_policy_lock:
        if _trust_policy is None:
            _trust_policy = TrustPolicy()
        return _trust_policy
