"""
Whisper Talk
============
A quiet-mode variant, not a separate voice pipeline - it wraps
ultron_voice.py rather than natural_speak.py directly, so whisper mode
still carries personality's style on top of its own lower volume/rate,
the same layering ultron_voice.py itself uses over natural_speak.py.
Nothing here is real audio whispering (that would need a different
synthesis voice, not just gain reduction) - "whisper" means "quiet and
unhurried", labeled honestly rather than promising an effect this
project's TTS engine can't produce.
"""

from typing import Dict, Optional

WHISPER_RATE_ADJUST = -30  # words/min, applied on top of ultron_voice's own style adjustment
WHISPER_VOLUME = 0.35


class WhisperTalk:
    """Quiet-mode speech via ultron_voice.py. Use get_whisper_talk()."""

    def speak(self, text: str) -> Dict:
        """Same return shape as ultron_voice.speak() - {"text", "spoken",
        "rate", "volume"} - with rate reduced and volume fixed low.
        Still routes through ultron_voice.py, so silent_mode.py is
        still honored (a whispered reply is not an exception to
        silent mode)."""
        try:
            from mouth.ultron_voice import get_ultron_voice
            from mouth.natural_speak import get_natural_speak
            from mouth.silent_mode import get_silent_mode

            if get_silent_mode().is_silent():
                return {"text": text, "spoken": False, "rate": None, "volume": WHISPER_VOLUME}

            base_rate, _ = get_ultron_voice()._styled_params()
            rate = max(80, base_rate + WHISPER_RATE_ADJUST)
            spoken = get_natural_speak().speak(text, rate=rate, volume=WHISPER_VOLUME)
            return {"text": text, "spoken": spoken, "rate": rate, "volume": WHISPER_VOLUME}
        except Exception:
            return {"text": text, "spoken": False, "rate": None, "volume": WHISPER_VOLUME}


_whisper_talk: Optional[WhisperTalk] = None


def get_whisper_talk() -> WhisperTalk:
    global _whisper_talk
    if _whisper_talk is None:
        _whisper_talk = WhisperTalk()
    return _whisper_talk
