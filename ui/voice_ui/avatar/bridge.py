"""
ui.voice_ui.avatar.bridge - connects AvatarController to core.events.

Phase 13: every other ui/ surface (dashboard, overlay, tray, orb) already
subscribes to core.events to drive its own state; avatar/states.py's
AvatarController was the one exception - it's a clean, dependency-free
state machine, but nothing ever called .transition() on it. This module
is the wiring, following the exact event -> state mapping already
documented in states.py's own docstring:

    wake word detected      -> LISTENING
    STT finished, sent to AI -> THINKING
    TTS playback started    -> SPEAKING
    TTS playback finished / STT idle -> IDLE
    any pipeline exception  -> ERROR (auto-recovers to IDLE)

Since core.events doesn't have distinct STT-finished/TTS-finished topics
yet (only thinking_start/speaking_start/speaking_end/response_ready/
wake_detected - see core/events.py's own docstring on what main.py
actually emits), this maps onto the closest existing ones. When a real
voice.* pipeline lands with finer-grained events, only the subscriptions
below need to change - callers of get_avatar_controller() don't.
"""

from __future__ import annotations

import threading
from typing import Optional

from core.events import get_event_bus
from core.logger import get_logger
from ui.voice_ui.avatar.states import AvatarController, AvatarState, InvalidTransition

logger = get_logger("ultron.ui.voice_ui.avatar")

ERROR_RECOVER_SECONDS = 5.0

_controller: Optional[AvatarController] = None
_wired = False
_recover_timer: Optional[threading.Timer] = None


def _safe_transition(state: AvatarState, detail: Optional[str] = None):
    global _recover_timer
    controller = get_avatar_controller()
    try:
        controller.transition(state, detail=detail)
    except InvalidTransition:
        # e.g. two "thinking" triggers back to back with no state in
        # between - not a bug, just two overlapping events; log and move
        # on rather than letting a bad transition kill the subscriber.
        logger.debug(f"avatar: ignored invalid transition to {state} from {controller.state}")
        return

    if _recover_timer is not None:
        _recover_timer.cancel()
        _recover_timer = None

    if state == AvatarState.ERROR:
        _recover_timer = threading.Timer(ERROR_RECOVER_SECONDS, controller.reset)
        _recover_timer.daemon = True
        _recover_timer.start()


def _wire(controller: AvatarController):
    global _wired
    if _wired:
        return
    _wired = True
    bus = get_event_bus()

    bus.subscribe("wake_detected", lambda **kw: _safe_transition(AvatarState.LISTENING))
    bus.subscribe("thinking_start", lambda **kw: _safe_transition(AvatarState.THINKING, kw.get("text")))
    bus.subscribe("speaking_start", lambda **kw: _safe_transition(AvatarState.SPEAKING))
    bus.subscribe("speaking_end", lambda **kw: _safe_transition(AvatarState.IDLE))
    bus.subscribe("response_ready", lambda **kw: _safe_transition(AvatarState.IDLE, kw.get("text")))
    bus.subscribe("error", lambda **kw: _safe_transition(AvatarState.ERROR, kw.get("text")))


def get_avatar_controller() -> AvatarController:
    """Process-wide singleton, wired to core.events on first access - same
    pattern as core.events.get_event_bus() and ui.tray.tray.get_tray().
    Renderers (a future desktop overlay, a web_ui panel over websocket)
    call this and controller.on_change(callback) to render against it;
    they never need to call .transition() themselves."""
    global _controller
    if _controller is None:
        _controller = AvatarController()
    _wire(_controller)
    return _controller
