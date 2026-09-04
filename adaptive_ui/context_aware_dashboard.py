"""
Context-aware dashboard
==========================
ui/dashboard/dashboard.py already shows a live status window (state,
activity log, API usage, sessions) unconditionally - every panel, every
time. This module sits on top of it and decides *which* of this phase's
extra signals are worth surfacing right now, posting them onto the same
dashboard window via its existing thread-safe post() queue rather than
opening a second window - one status surface, not two competing ones.

Context sources (each optional - degrades gracefully if a given
sub-package isn't active):
    - VOICE_INTELLIGENCE: current speaker (speaker_diarization), mood
      (emotion_analyzer), whether full_duplex_engine is mid-turn
    - COMPUTER_VISION: latest anomaly_detector.py finding
    - PHASE_17_4 swarm: active subtask count, if the orchestrator is
      mid-request (read via phase16_bridge's events, not a direct import,
      so this module doesn't need to know swarm internals)

Posts through the dashboard's existing "log" event (see dashboard.py's
on_event handler, which only understands "state"/"log"/"notification")
rather than inventing a new event name dashboard.py would need to be
taught - this stays purely additive, no change to dashboard.py itself.
"""

from typing import Dict, Optional

from ui.dashboard.dashboard import open_dashboard
from core_integration.phase16_bridge import get_bridge
from core.logger import get_logger

logger = get_logger("ultron.interaction.context_dashboard")


class ContextAwareDashboard:
    """Thin controller over ui/dashboard.py - opens it if needed and
    keeps pushing this phase's context onto it via subscriptions on the
    unified event bus, rather than polling."""

    def __init__(self):
        self._bridge = get_bridge()
        self._wired = False
        self._unsubscribers = []

    def open(self) -> None:
        open_dashboard()
        self._wire()

    def _post(self, label: str, value: str) -> None:
        """Post a "log" line - the one _on_event event name that renders
        free-form text without needing dashboard.py itself changed (it
        only understands "state"/"log"/"notification" - see its module
        docstring/on_event handler)."""
        import ui.dashboard.dashboard as dash_module

        win = dash_module._window
        if win is not None:
            win.post("log", line=f"[{label}] {value}")

    def _wire(self) -> None:
        if self._wired:
            return
        self._wired = True

        events = self._bridge.events
        self._unsubscribers = [
            events.subscribe("interaction:heard", lambda **data: self._post("Heard", data.get("text", ""))),
            events.subscribe("interaction:barge_in", lambda **data: self._post("Barge-in", "user interrupted")),
            events.subscribe("interaction:replying", lambda **data: self._post("Replying", data.get("text", "")[:80])),
            events.subscribe(
                "swarm:request_started",
                lambda **data: self._post("Swarm", f"working on: {data.get('request', '')[:60]}"),
            ),
            events.subscribe("swarm:request_completed", lambda **data: self._post("Swarm", "request completed")),
        ]
        logger.info("Context-aware dashboard wired to unified event bus")

    def unwire(self) -> None:
        for unsub in self._unsubscribers:
            try:
                unsub()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("adaptive_ui.context_aware_dashboard.unwire")
        self._unsubscribers = []
        self._wired = False

    def push_mood(self, mood: str, speaker: Optional[str] = None) -> None:
        """Convenience for callers using emotion_analyzer.py/speaker_diarization.py
        directly to surface a reading without waiting for an event."""
        label = f"Mood ({speaker})" if speaker else "Mood"
        self._post(label, mood)

    def push_anomaly(self, finding: Dict) -> None:
        if finding.get("is_anomaly"):
            hits = ", ".join(h["keyword"] for h in finding.get("keyword_hits", [])[:3])
            self._post("Screen alert", hits or "unexpected screen change")


_dashboard: Optional[ContextAwareDashboard] = None


def get_context_dashboard() -> ContextAwareDashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = ContextAwareDashboard()
    return _dashboard
