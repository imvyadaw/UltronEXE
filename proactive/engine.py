"""
Proactive engine
================
The background loop that makes Ultron speak up without being asked:
every POLL_INTERVAL_SECONDS it polls threshold_alerts, time_based, and
event_driven triggers, turns any due events into ULTRON-voiced text via
conversation/response_builder.py, and delivers them through
ui/notifications.py (so every UI surface - tray, dashboard, overlay -
sees it the same way it already sees other notifications) and, if a
speak callback was registered, out loud via TTS.

Runs on its own daemon thread so it never blocks the main assistant
loop (voice listening, text input) in main.py / core/assistant.py.
Entirely best-effort: any exception in a single tick is logged and
swallowed so one bad monitor reading can't kill the whole loop, matching
the "optional feature degrades, never crashes the app" philosophy used
throughout core/ and ui/.

Wiring it up (optional - Ultron works fine without ever starting this):

    from proactive.engine import get_proactive_engine
    get_proactive_engine().start(speak_callback=ultron_runtime.speak)
"""

import threading
from typing import Callable, Dict, List, Optional

from proactive.triggers.threshold_alerts import get_threshold_alerts
from proactive.triggers.time_based import get_time_based_triggers
from proactive.triggers.event_driven import get_event_driven_triggers
from proactive.predictor import get_action_predictor
from proactive.suggester import get_suggestion_engine
from proactive.automatic_actions import get_automatic_action_executor
from proactive.disruption_guard import get_disruption_guard
from proactive.monitors.user_activity import get_user_activity_monitor
from conversation.response_builder import get_response_builder
from ui.notifications import notify
from core.events import get_event_bus
from core.logger import get_logger

logger = get_logger("ultron.proactive.engine")

POLL_INTERVAL_SECONDS = 30


class ProactiveEngine:
    """Background loop wiring proactive/triggers + conversation/response_builder
    + ui.notifications together. See module docstring."""

    def __init__(self, poll_interval: float = POLL_INTERVAL_SECONDS):
        self._poll_interval = poll_interval
        self._threshold = get_threshold_alerts()
        self._time_based = get_time_based_triggers()
        self._event_driven = get_event_driven_triggers()
        self._response_builder = get_response_builder()
        self._events = get_event_bus()

        # Phase 25 - predictive suggestion + automatic-action pipeline.
        # predictor learns passively via core.event_bus (see predictor.py),
        # so it needs no wiring here beyond being constructed once.
        self._predictor = get_action_predictor()
        self._suggester = get_suggestion_engine()
        self._auto_actions = get_automatic_action_executor()
        self._disruption_guard = get_disruption_guard()
        self._activity = get_user_activity_monitor()

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._speak_callback: Optional[Callable[[str], None]] = None
        # Scenario runners registered by category (see scenarios/*.py's
        # register_with_engine() helpers) - lets a time_based "morning_briefing"
        # slot run the actual MorningRoutine instead of just reading a canned line.
        self._scenario_handlers: Dict[str, Callable[[], Optional[str]]] = {}

    # -- registration -----------------------------------------------------
    def register_scenario(self, category: str, handler: Callable[[], Optional[str]]) -> None:
        """Register a callable that fully handles a category (e.g. runs
        MorningRoutine and returns its own briefing text) instead of the
        engine falling back to a generic phrase-bank line for it."""
        self._scenario_handlers[category] = handler

    def watch_file(self, path: str, recursive: bool = False) -> Dict:
        """Convenience passthrough so callers don't need to import
        proactive.triggers.event_driven directly just to add a file watch."""
        return self._event_driven.watch_path(path, recursive=recursive)

    # -- lifecycle ----------------------------------------------------------
    def start(self, speak_callback: Optional[Callable[[str], None]] = None) -> None:
        """Starts the background poll loop. Safe to call once; a second call
        while already running is a no-op (won't spawn a duplicate thread)."""
        if self._thread and self._thread.is_alive():
            logger.info("Proactive engine already running.")
            return
        self._speak_callback = speak_callback
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="proactive-engine")
        self._thread.start()
        logger.info("Proactive engine started.")

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Proactive engine stopped.")

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- loop -----------------------------------------------------------
    def _run_loop(self) -> None:
        while not self._stop_flag.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Proactive engine tick failed: {e}")
            self._stop_flag.wait(self._poll_interval)

    def _tick(self) -> None:
        events: List[Dict] = []
        events.extend(self._threshold.check())
        events.extend(self._time_based.check())
        events.extend(self._event_driven.check())

        for event in events:
            self._handle_event(event["category"], event.get("kwargs", {}))

        self._tick_suggestions()

    def _tick_suggestions(self) -> None:
        """Phase 25: predictor -> suggester -> (automatic_actions | ask).
        Runs after the existing trigger events so a hard threshold alert
        (CPU/battery/etc.) always takes priority in a given tick over a
        soft "you usually do X now" nudge."""
        try:
            context = self._activity.snapshot()
            suggestions = self._suggester.generate(context=context)
        except Exception as e:
            logger.error(f"Proactive suggestion generation failed: {e}")
            return

        for suggestion in suggestions:
            try:
                self._handle_suggestion(suggestion)
            except Exception as e:
                logger.error(f"Handling suggestion for '{suggestion.get('action_name')}' failed: {e}")

    def _handle_suggestion(self, suggestion: Dict) -> None:
        auto_result = self._auto_actions.consider(suggestion)
        if auto_result.get("executed"):
            # automatic_actions.py already notified + emitted the event;
            # still surface it on the legacy bus like every other alert
            # so ui/tray, ui/dashboard, ui/overlay see it the same way.
            self._events.emit(
                "proactive_alert",
                category="proactive_auto_action",
                text=suggestion["text"],
                level="info",
            )
            return

        decision = self._disruption_guard.check("proactive_suggestion", urgency="normal")
        if decision["decision"] != "allow":
            logger.debug(f"Suggestion for '{suggestion['action_name']}' held back: {decision['reason']}")
            return

        self._deliver("proactive_suggestion", suggestion["text"], level="info")

    def _handle_event(self, category: str, kwargs: Dict) -> None:
        handler = self._scenario_handlers.get(category)
        if handler is not None:
            try:
                text = handler()
            except Exception as e:
                logger.error(f"Scenario handler for '{category}' failed: {e}")
                text = None
            if text:
                self._deliver(category, text, level="info")
            return

        phrase = self._response_builder.build_alert(category, **kwargs)
        self._deliver(category, phrase["text"], level=phrase["level"])

    def _deliver(self, category: str, text: str, level: str = "info") -> None:
        notify(title="Ultron", message=text, level=level, source=f"proactive.{category}")
        self._events.emit("proactive_alert", category=category, text=text, level=level)
        if self._speak_callback is not None:
            try:
                self._speak_callback(text)
            except Exception as e:
                logger.error(f"Speak callback failed for proactive alert: {e}")


_engine: Optional[ProactiveEngine] = None
_engine_lock = threading.Lock()


def get_proactive_engine() -> ProactiveEngine:
    """Process-wide singleton, same pattern as core.brain.get_brain() /
    core.events.get_event_bus()."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ProactiveEngine()
        return _engine
