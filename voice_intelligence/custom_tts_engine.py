"""
Custom TTS engine
====================
A thin prosody layer over voice/tts/tts_engine.py's UltronVoice - maps a
mood (from emotion_analyzer.py) or a named persona preset to concrete
set_rate()/set_pitch()/set_voice() calls, then delegates the actual
synthesis/playback/caching/streaming entirely to UltronVoice, which
already does all of that well. This module adds *what settings to use*,
not a new synthesis path.

Settings are applied for one utterance and then restored, so a mood-
driven tweak for an excited reply doesn't leak into the next, unrelated
sentence - UltronVoice itself is a shared singleton (get_voice()) with
no concept of "for this call only", so save/restore is done here.
"""

from contextlib import contextmanager
from typing import Dict, Optional

from voice.tts.tts_engine import get_voice
from core.logger import get_logger

logger = get_logger("ultron.interaction.custom_tts")

# rate_percent is relative to the backend's normal rate; pitch_hz is an
# absolute offset understood by set_pitch() (backend-dependent, best-effort
# for backends that don't support pitch - see UltronVoice.set_pitch).
MOOD_PROSODY = {
    "upbeat": {"rate": 12, "pitch": 15},
    "tense": {"rate": -5, "pitch": -10},
    "subdued": {"rate": -15, "pitch": -20},
    "neutral": {"rate": 0, "pitch": 0},
}

# Named persona presets - a voice + baseline prosody a caller can pick
# explicitly (e.g. "reply in a calm, formal tone") independent of the
# detected mood; mood adjustments still layer on top of these.
PERSONA_PRESETS = {
    "default": {"voice": None, "rate": 0, "pitch": 0},
    "calm": {"voice": None, "rate": -8, "pitch": -5},
    "energetic": {"voice": None, "rate": 10, "pitch": 10},
    "formal": {"voice": None, "rate": -5, "pitch": 0},
}


@contextmanager
def _temporary_prosody(rate: int, pitch: int, voice: Optional[str]):
    v = get_voice()
    try:
        if voice:
            v.set_voice(voice)
        if rate:
            v.set_rate(rate)
        if pitch:
            v.set_pitch(pitch)
        yield v
    finally:
        # Restore neutral defaults rather than trying to snapshot/restore
        # the prior arbitrary values - simpler, and "neutral" is always a
        # safe baseline for the next unrelated utterance.
        if voice:
            pass  # voice choice is left as-is; switching every utterance is jarring
        if rate:
            v.set_rate(0)
        if pitch:
            v.set_pitch(0)


class CustomTTSEngine:
    """Mood/persona-aware wrapper around UltronVoice. Stateless beyond
    UltronVoice's own singleton state - safe to share."""

    def speak(self, text: str, mood: str = "neutral", persona: str = "default", blocking: bool = True) -> Dict:
        preset = PERSONA_PRESETS.get(persona, PERSONA_PRESETS["default"])
        mood_adj = MOOD_PROSODY.get(mood, MOOD_PROSODY["neutral"])

        rate = preset["rate"] + mood_adj["rate"]
        pitch = preset["pitch"] + mood_adj["pitch"]
        voice = preset["voice"]

        try:
            with _temporary_prosody(rate=rate, pitch=pitch, voice=voice) as v:
                v.speak(text, blocking=blocking)
            return {"success": True, "mood": mood, "persona": persona, "rate": rate, "pitch": pitch}
        except Exception as e:
            logger.warning(f"Custom TTS speak failed, falling back to plain speak: {e}")
            try:
                get_voice().speak(text, blocking=blocking)
                return {"success": True, "mood": mood, "persona": persona, "fallback": True}
            except Exception as e2:
                return {"error": str(e2)}

    def speak_with_emotion(self, text: str, audio=None, persona: str = "default", blocking: bool = True) -> Dict:
        """Convenience: run emotion_analyzer.py on the given audio/text
        and speak the reply with matching prosody in one call."""
        from voice_intelligence.emotion_analyzer import get_emotion_analyzer

        result = get_emotion_analyzer().analyze(audio=audio, text=text)
        return self.speak(text, mood=result.get("mood", "neutral"), persona=persona, blocking=blocking)


_engine: Optional[CustomTTSEngine] = None


def get_custom_tts() -> CustomTTSEngine:
    global _engine
    if _engine is None:
        _engine = CustomTTSEngine()
    return _engine
