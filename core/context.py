"""
Context
=======
Tracks richer situational context alongside the flat conversation
history that already lives on ai.cloud_models.groq_client.UltronGroqClient
(self.conversation_history) - active app, current working directory,
and a bounded window of recent tool results, so a future planner or
agent can answer "what was I just doing" without re-reading the whole
conversation.
"""

import time
from pathlib import Path
from typing import Dict, List, Optional

MAX_RECENT_TOOL_RESULTS = 20

_context: Optional["ConversationContext"] = None


class ConversationContext:
    """Lightweight situational state: active app, cwd, recent tool results."""

    def __init__(self):
        self.active_app: Optional[str] = None
        self.current_directory: str = str(Path.home())
        self._recent_tool_results: List[Dict] = []

    def set_active_app(self, app_name: str) -> None:
        self.active_app = app_name

    def set_current_directory(self, path: str) -> None:
        self.current_directory = path

    def record_tool_result(self, tool_name: str, arguments: Dict, result: Dict) -> None:
        """Remember a tool call + its result, most recent last, capped at
        MAX_RECENT_TOOL_RESULTS entries."""
        self._recent_tool_results.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
                "timestamp": time.time(),
            }
        )
        if len(self._recent_tool_results) > MAX_RECENT_TOOL_RESULTS:
            self._recent_tool_results.pop(0)

    def get_recent_tool_results(self, limit: int = 5) -> List[Dict]:
        """Most recent tool calls, most recent last."""
        return self._recent_tool_results[-limit:]

    def last_result_for(self, tool_name: str) -> Optional[Dict]:
        """The most recent result for a specific tool, if any."""
        for entry in reversed(self._recent_tool_results):
            if entry["tool"] == tool_name:
                return entry
        return None

    def snapshot(self) -> Dict:
        """Everything currently tracked, for logging/debugging or handing to a planner."""
        return {
            "active_app": self.active_app,
            "current_directory": self.current_directory,
            "recent_tool_calls": len(self._recent_tool_results),
        }


def get_context() -> ConversationContext:
    """Process-wide singleton, same pattern as core.brain.get_brain() /
    core.events.get_event_bus(). Was missing before, which meant every
    caller's `from core.context import get_context` silently failed
    (caught by their own try/except) and context_facts always came back
    None."""
    global _context
    if _context is None:
        _context = ConversationContext()
    return _context
