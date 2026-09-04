"""
Unified Context (Phase 21 - Unified Core Architecture)
=======================================================
Before this, "what's going on right now" was split across four places
with no single read: core/context.py (active app, cwd, recent tool
results), core/consciousness.py (focus stack, confidence),
core/goal_manager.py (the active goal), and core/user_manager.py (who's
talking). action_pipeline and response_manager both need all four at
once - the pipeline to decide what's allowed and the response manager
to decide how to phrase things - so this module is a read-through
facade that composes them into one snapshot() instead of every caller
re-collecting the same four imports.

This module holds no state of its own beyond a bounded response-history
log (response_manager.record_response); everything else is a live
delegate to the owning module, so there's exactly one source of truth
per fact and unified_context never goes stale.
"""

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

MAX_RESPONSE_HISTORY = 30


class UnifiedContext:
    """Process-wide read-through composite. Use get_unified_context()."""

    def __init__(self):
        self._response_history: Deque[Dict] = deque(maxlen=MAX_RESPONSE_HISTORY)

    # -- situational (core.context) -----------------------------------
    @property
    def conversation_context(self):
        from core.context import ConversationContext

        if not hasattr(self, "_conv_ctx"):
            self._conv_ctx = ConversationContext()
        return self._conv_ctx

    # -- attention / confidence (core.consciousness) --------------------
    def focus(self) -> Optional[str]:
        try:
            from core.consciousness import get_consciousness

            return get_consciousness().current_focus
        except Exception:
            return None

    def confidence(self) -> float:
        try:
            from core.consciousness import get_consciousness

            return get_consciousness().confidence
        except Exception:
            return 0.5

    # -- active goal (core.goal_manager) ---------------------------------
    def active_goal(self) -> Optional[Dict]:
        try:
            from core.goal_manager import get_goal_manager

            return get_goal_manager().active_goal()
        except Exception:
            return None

    # -- active user (core.user_manager) ---------------------------------
    def active_user(self) -> Optional[Dict]:
        try:
            from core.user_manager import get_user_manager

            return get_user_manager().get_active_user()
        except Exception:
            return None

    # -- response history --------------------------------------------------
    def record_response(self, channel: str, text: str, meta: Optional[Dict] = None) -> None:
        self._response_history.append(
            {
                "channel": channel,
                "text": text,
                "meta": meta or {},
                "timestamp": time.time(),
            }
        )

    def recent_responses(self, limit: int = 5) -> List[Dict]:
        return list(self._response_history)[-limit:]

    # -- rollup ----------------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """Everything a planner/response formatter needs in one dict.
        Every field is best-effort - a missing subsystem yields None
        rather than raising, so callers never need their own try/except."""
        cc = self.conversation_context
        user = self.active_user()
        goal = self.active_goal()
        return {
            "active_app": cc.active_app,
            "current_directory": cc.current_directory,
            "recent_tool_calls": cc.get_recent_tool_results(limit=5),
            "focus": self.focus(),
            "confidence": self.confidence(),
            "active_goal": goal.get("title") if goal else None,
            "active_goal_id": goal.get("id") if goal else None,
            "active_user": user.get("username") if user else None,
            "recent_responses": self.recent_responses(limit=3),
        }


_context: Optional[UnifiedContext] = None


def get_unified_context() -> UnifiedContext:
    global _context
    if _context is None:
        _context = UnifiedContext()
    return _context
