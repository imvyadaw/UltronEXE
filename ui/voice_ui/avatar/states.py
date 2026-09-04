"""
ui.voice_ui.avatar.states - avatar state machine.

Not wired to the actual voice pipeline yet (there's no import of a
`voice.*` module here on purpose - Phase 5/6 don't expose one, per
docs/architecture/phase6_config_storage.md). This is the target
interface: whatever drives wake-word detection / STT / TTS should
call `AvatarController.transition(...)` at the matching points once
that wiring exists. Any renderer (a desktop overlay, a web_ui panel
over websocket, etc.) subscribes with `on_change`.

Expected call sites once wired, matching config/default.yaml's
`voice:` section:
    - wake word ("ultron") detected      -> LISTENING
    - STT finished, request sent to AI   -> THINKING
    - TTS playback started               -> SPEAKING
    - TTS playback finished / STT idle   -> IDLE
    - any pipeline exception             -> ERROR (auto-recovers to IDLE)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class AvatarState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


# States each state is allowed to move to. Anything can move to ERROR,
# and ERROR always recovers to IDLE - see AvatarController.transition.
_ALLOWED_TRANSITIONS = {
    AvatarState.IDLE: {AvatarState.LISTENING, AvatarState.ERROR},
    AvatarState.LISTENING: {AvatarState.THINKING, AvatarState.IDLE, AvatarState.ERROR},
    AvatarState.THINKING: {AvatarState.SPEAKING, AvatarState.IDLE, AvatarState.ERROR},
    AvatarState.SPEAKING: {AvatarState.IDLE, AvatarState.LISTENING, AvatarState.ERROR},
    AvatarState.ERROR: {AvatarState.IDLE},
}


@dataclass
class AvatarEvent:
    state: AvatarState
    previous: AvatarState
    timestamp: float = field(default_factory=time.time)
    detail: str | None = None


class InvalidTransition(Exception):
    pass


class AvatarController:
    """
    Tiny observer-pattern state machine. No I/O, no rendering - just
    the state and validation, so it's easy to drive from tests or from
    whatever the eventual voice pipeline looks like.
    """

    def __init__(self) -> None:
        self._state = AvatarState.IDLE
        self._listeners: list[Callable[[AvatarEvent], None]] = []

    @property
    def state(self) -> AvatarState:
        return self._state

    def on_change(self, callback: Callable[[AvatarEvent], None]) -> None:
        self._listeners.append(callback)

    def transition(self, new_state: AvatarState, detail: str | None = None) -> AvatarEvent:
        if new_state != AvatarState.ERROR and new_state not in _ALLOWED_TRANSITIONS[self._state]:
            raise InvalidTransition(f"{self._state} -> {new_state} is not allowed")

        event = AvatarEvent(state=new_state, previous=self._state, detail=detail)
        self._state = new_state
        for listener in self._listeners:
            listener(event)
        return event

    def reset(self) -> AvatarEvent:
        return self.transition(AvatarState.IDLE, detail="reset")
