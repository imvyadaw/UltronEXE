"""
Multi-modal input
====================
Fuses voice, gesture, and screen-click events from across this phase
into one input stream, so a caller (an app loop, a game, an
accessibility flow) can subscribe once instead of separately watching
full_duplex_engine.py's transcripts, gesture_controller.py's confirmed
gestures, and raw mouse clicks.

Doesn't introduce a new transport - every source already emits on the
unified event bus (interaction:heard, interaction:gesture,
interaction:barge_in, ...); this module just subscribes to all of them
and republishes a single normalized "interaction:input" event with a
consistent {"modality", "value", "raw"} shape, plus a short in-memory
history so a caller that starts watching mid-session can see recent
inputs instead of only ones from this exact moment forward.

Click/keyboard input isn't captured globally in this project (no system-
wide input hook module exists - visual_automator.py only *emits*
clicks, it doesn't listen for the user's own), so the "click" modality
here is populated only by whatever a caller explicitly reports via
report_click() - e.g. a generative_ui_builder.py panel's button handler
- not passively captured from anywhere on the screen.
"""

from collections import deque
from typing import Callable, Deque, Dict, List, Optional

from core_integration.phase16_bridge import get_bridge
from core.logger import get_logger

logger = get_logger("ultron.interaction.multimodal")

DEFAULT_HISTORY = 50


class MultiModalInputFuser:
    """Subscribes to this phase's voice/gesture events once, republishes
    a normalized stream, and keeps a short history. One instance is
    enough for a whole session - get_fuser() below provides that
    singleton; construct your own only if you need isolated history
    (e.g. two independent input contexts in the same process)."""

    def __init__(self, history_size: int = DEFAULT_HISTORY):
        self._bridge = get_bridge()
        self._history: Deque[Dict] = deque(maxlen=history_size)
        self._subscribers: List[Callable[[Dict], None]] = []
        self._wired = False

    def on_input(self, callback: Callable[[Dict], None]) -> Callable[[], None]:
        """Register a callback invoked with each normalized input event.
        Returns an unsubscribe function."""
        self._subscribers.append(callback)

        def _unsubscribe():
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return _unsubscribe

    def _publish(self, modality: str, value, raw: Dict) -> None:
        event = {"modality": modality, "value": value, "raw": raw}
        self._history.append(event)
        self._bridge.events.emit("interaction:input", modality=modality, value=value, raw=raw)
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"Multi-modal input subscriber failed: {e}")

    def report_click(self, target: str, position: Optional[Dict] = None) -> None:
        """Callers with their own click source (e.g. a generative UI
        panel) report it here so it joins the same normalized stream as
        voice/gesture input - see module docstring for why this project
        has no passive global click capture."""
        self._publish("click", target, {"target": target, "position": position})

    def _wire(self) -> None:
        if self._wired:
            return
        self._wired = True
        events = self._bridge.events

        events.subscribe("interaction:heard", lambda **data: self._publish("voice", data.get("text", ""), data))
        events.subscribe(
            "interaction:gesture",
            lambda **data: self._publish("gesture", data.get("action", data.get("gesture", "")), data),
        )
        events.subscribe("interaction:barge_in", lambda **data: self._publish("voice_interrupt", True, data))
        logger.info("Multi-modal input fuser wired to unified event bus")

    def start(self) -> None:
        self._wire()

    def recent(self, modality: Optional[str] = None, limit: int = 10) -> List[Dict]:
        items = list(self._history)
        if modality:
            items = [i for i in items if i["modality"] == modality]
        return items[-limit:]


_fuser: Optional[MultiModalInputFuser] = None


def get_fuser() -> MultiModalInputFuser:
    global _fuser
    if _fuser is None:
        _fuser = MultiModalInputFuser()
    return _fuser
