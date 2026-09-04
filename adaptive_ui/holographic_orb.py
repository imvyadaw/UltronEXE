"""
Holographic orb (extended)
=============================
ui/orb/orb.py already renders the HUD orb and reacts to a fixed
set of states (idle/listening/thinking/speaking/tool/error) driven by
core.events. This module doesn't add new visual states to the orb
itself (STATE_PALETTE/STATE_LABELS are a closed set baked into orb.py's
rendering - changing that is out of scope for a wrapper) - instead it
reuses the existing "state" event's optional caption text to surface
this phase's extra signals on top of the states orb.py already knows
how to draw:

    - barge-in           -> state("listening", "Go ahead, I'm listening")
    - diarized speaker    -> appended to the next state's caption, e.g.
                             "Alice: what's the weather" instead of just
                             "what's the weather"
    - detected mood        -> a short mood tag appended to the caption
                             when confidence is reasonably high, e.g.
                             "(sounding upbeat)"

This keeps ui/orb/orb.py completely untouched - every update here still
goes through open_orb()'s own win.post("state", ...) queue, the same
thread-safe path core.events-driven updates already use.
"""

from typing import Optional

from ui.orb.orb import open_orb, is_orb_open
from core_integration.phase16_bridge import get_bridge
from core.logger import get_logger

logger = get_logger("ultron.interaction.holographic_orb")

MOOD_CAPTION = {
    "upbeat": "sounding upbeat",
    "tense": "sounding tense",
    "subdued": "sounding low-energy",
}


class HolographicOrb:
    """Extra-signal layer over ui/orb/orb.py. Call open() once, then use
    the annotate_* helpers to piggyback speaker/mood info onto whatever
    state the orb is already showing."""

    def __init__(self):
        self._bridge = get_bridge()
        self._last_speaker: Optional[str] = None
        self._last_mood: Optional[str] = None
        self._wired = False

    def open(self) -> None:
        open_orb()
        self._wire()

    @property
    def is_open(self) -> bool:
        return is_orb_open()

    def _post_state(self, state: str, caption: Optional[str] = None) -> None:
        import ui.orb.orb as orb_module

        win = orb_module._window
        if win is not None:
            win.post("state", state=state, text=caption)

    def _compose_caption(self, base_text: str) -> str:
        parts = []
        if self._last_speaker:
            parts.append(f"{self._last_speaker}:")
        parts.append(base_text)
        if self._last_mood and self._last_mood in MOOD_CAPTION:
            parts.append(f"({MOOD_CAPTION[self._last_mood]})")
        return " ".join(parts)

    def annotate_speaker(self, speaker_label: str) -> None:
        self._last_speaker = speaker_label

    def annotate_mood(self, mood: str) -> None:
        self._last_mood = mood

    def show_heard(self, text: str) -> None:
        self._post_state("listening", self._compose_caption(text))

    def show_barge_in(self) -> None:
        self._post_state("listening", "Go ahead, I'm listening")

    def _wire(self) -> None:
        if self._wired:
            return
        self._wired = True
        events = self._bridge.events
        events.subscribe("interaction:heard", lambda **data: self.show_heard(data.get("text", "")))
        events.subscribe("interaction:barge_in", lambda **data: self.show_barge_in())
        logger.info("Holographic orb wired to unified event bus")


_orb: Optional[HolographicOrb] = None


def get_holographic_orb() -> HolographicOrb:
    global _orb
    if _orb is None:
        _orb = HolographicOrb()
    return _orb
