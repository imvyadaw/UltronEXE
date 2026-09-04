"""
Gesture controller
=====================
Maps vision/gestures/recognizer.py's per-hand gesture labels (fist,
open_palm, peace, thumbs_up, pointing, ...) to concrete Ultron actions,
dispatched as events on the unified bus rather than this module calling
into agents/skills directly - keeps this a thin "gesture -> named
intent" layer, with whatever's actually listening (full_duplex_engine.py
for "stop", context_aware_dashboard.py for a UI dismiss, etc.) deciding
what to do about it. Same separation multi_modal_input.py relies on to
fuse this with voice/click events without needing to know gesture
specifics.

GestureRecognizer.detect() takes any PIL Image (defaulting to a
screen capture if none given, per its own docstring) - for gestures that
default is the wrong source (you gesture at a camera, not your screen),
so this controller expects the caller to supply webcam frames explicitly;
no camera-capture module exists in this project yet (see module search),
so wiring an actual webcam feed in is left to the caller.

Debounced the same way voice_activity_detector.py debounces speech:
requires the same gesture to repeat across consecutive frames before
firing, so a single misread frame mid-gesture doesn't trigger an action.
"""

from typing import Callable, Dict, Optional

from vision.gestures.recognizer import GestureRecognizer
from core_integration.phase16_bridge import get_bridge
from core.logger import get_logger

logger = get_logger("ultron.interaction.gesture_controller")

# gesture label -> (event name, human-readable action) fired on the
# unified bus when the gesture is confirmed (see CONFIRM_FRAMES).
GESTURE_ACTIONS = {
    "open_palm": ("interaction:gesture_stop", "stop"),
    "fist": ("interaction:gesture_cancel", "cancel"),
    "thumbs_up": ("interaction:gesture_confirm", "confirm"),
    "peace": ("interaction:gesture_dismiss", "dismiss"),
    "pointing": ("interaction:gesture_select", "select"),
}

CONFIRM_FRAMES = 3  # consecutive matching frames required before firing


class GestureController:
    """Stateful per-stream debouncer + dispatcher - one instance per
    camera/session, since it tracks a running streak of the last-seen
    gesture."""

    def __init__(self, on_action: Optional[Callable[[str, str], None]] = None):
        self._recognizer = GestureRecognizer()
        self._bridge = get_bridge()
        self._on_action = on_action
        self._last_gesture: Optional[str] = None
        self._streak = 0
        self._fired_for_streak = False

    def process_frame(self, image) -> Dict:
        """Feed one camera frame (a PIL Image). Returns the raw detection
        plus whether an action fired this call."""
        result = self._recognizer.detect(image=image)
        if "error" in result:
            return result

        hands = result.get("hands", [])
        gesture = hands[0]["gesture"] if hands else None

        if gesture == self._last_gesture and gesture is not None:
            self._streak += 1
        else:
            self._last_gesture = gesture
            self._streak = 1
            self._fired_for_streak = False

        fired = False
        if gesture in GESTURE_ACTIONS and self._streak >= CONFIRM_FRAMES and not self._fired_for_streak:
            event_name, action = GESTURE_ACTIONS[gesture]
            self._dispatch(gesture, event_name, action)
            self._fired_for_streak = True
            fired = True

        return {**result, "current_gesture": gesture, "streak": self._streak, "action_fired": fired}

    def _dispatch(self, gesture: str, event_name: str, action: str) -> None:
        logger.info(f"Gesture confirmed: {gesture} -> {action}")
        self._bridge.events.emit(event_name, gesture=gesture, action=action)
        self._bridge.events.emit("interaction:gesture", gesture=gesture, action=action)
        if self._on_action:
            try:
                self._on_action(gesture, action)
            except Exception as e:
                logger.warning(f"Gesture action callback failed: {e}")

    def reset(self) -> None:
        self._last_gesture = None
        self._streak = 0
        self._fired_for_streak = False


def get_gesture_controller(on_action: Optional[Callable[[str, str], None]] = None) -> GestureController:
    """New controller per call (mirroring speaker_diarization.get_diarizer's
    reasoning) - each camera/session needs its own debounce state, so no
    shared module-level singleton here."""
    return GestureController(on_action=on_action)
