"""
Silent Mode
===========
A single in-memory on/off toggle, deliberately this small - the same
"one flag, one job" restraint MEMORY/forget.py's forget_everything()
uses its confirm=True guard for, just for muting instead of deleting.
ultron_voice.py and whisper_talk.py both check is_silent() before
calling natural_speak.py and skip playback (while still returning the
spoken-would-be text) when it's on, so callers never have to
special-case silent mode themselves - text output keeps working, only
the audio device is skipped.

No persistence - like MEMORY/short_term.py, this is process-lifetime
state, not a durable preference. A caller wanting "always start
silent" should call enable() during startup, not expect this module to
remember it across restarts.
"""

from typing import Optional


class SilentMode:
    """Global mute toggle for MOUTH/. Use get_silent_mode()."""

    def __init__(self):
        self._silent = False

    def is_silent(self) -> bool:
        return self._silent

    def enable(self) -> None:
        self._silent = True

    def disable(self) -> None:
        self._silent = False

    def toggle(self) -> bool:
        self._silent = not self._silent
        return self._silent


_silent_mode: Optional[SilentMode] = None


def get_silent_mode() -> SilentMode:
    global _silent_mode
    if _silent_mode is None:
        _silent_mode = SilentMode()
    return _silent_mode
