"""
ElevenLabs TTS backend
========================
Real human-like / voice-cloned speech via the ElevenLabs REST API - the
"extreme level" voice upgrade over voice/tts/edge_tts.py's Microsoft
neural voices. Two ways to use it:

  1. Pick one of ElevenLabs' own hyper-realistic pretrained voices
     (set ELEVENLABS_VOICE_ID in .env to that voice's ID - find IDs at
     https://elevenlabs.io/app/voice-library).
  2. Clone a real voice: upload a short (1-2 min, clean, no background
     noise) audio sample at https://elevenlabs.io/app/voice-lab ->
     "Instant Voice Cloning" -> copy the resulting voice ID into
     ELEVENLABS_VOICE_ID. Every reply Ultron speaks after that uses
     that cloned voice.

Needs: pip install requests (already a dependency elsewhere in this
project) and an ElevenLabs API key - https://elevenlabs.io -> Profile ->
API Keys. Free tier exists (limited characters/month); paid tiers raise
the cap and unlock higher-quality models.

This module is synthesis-only (text -> mp3 file), same contract as
edge_tts.py/gtts_tts.py - voice/tts/tts_engine.py's UltronVoice handles
sentence chunking, caching, playback, and falling through to the next
configured backend if this one errors or the key/package is missing.
"""

from typing import Optional

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL,
    ELEVENLABS_STABILITY,
    ELEVENLABS_SIMILARITY_BOOST,
)
from core.logger import get_logger

logger = get_logger("elevenlabs_tts")

_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


class ElevenLabsTTSBackend:
    """Synthesis-only ElevenLabs backend - a plain blocking HTTPS POST
    per sentence, same as gtts_tts.py (no background event loop needed,
    unlike edge_tts.py's asyncio-based SDK)."""

    name = "elevenlabs"

    def __init__(
        self,
        api_key: str = ELEVENLABS_API_KEY,
        voice_id: str = ELEVENLABS_VOICE_ID,
        model: str = ELEVENLABS_MODEL,
        stability: float = ELEVENLABS_STABILITY,
        similarity_boost: float = ELEVENLABS_SIMILARITY_BOOST,
    ):
        if not HAS_REQUESTS:
            raise RuntimeError("requests not installed - run: pip install requests")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY not set - get one free at https://elevenlabs.io "
                "(Profile -> API Keys) and add it to .env"
            )
        if not voice_id:
            raise RuntimeError(
                "ELEVENLABS_VOICE_ID not set - pick a voice at "
                "https://elevenlabs.io/app/voice-library (or clone your own at "
                "https://elevenlabs.io/app/voice-lab) and copy its ID into .env"
            )
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.stability = stability
        self.similarity_boost = similarity_boost

    def synthesize(
        self, text: str, out_path: str, timeout: float = 8.0, voice_id: Optional[str] = None
    ) -> Optional[str]:
        """Render `text` to an mp3 file at `out_path`. Returns out_path on
        success, None on failure (caller falls through to the next
        configured TTS engine, e.g. edge/pyttsx3) - never raises, matching
        every other backend's contract so a network hiccup or an
        exhausted free-tier quota degrades gracefully instead of losing
        Ultron's voice entirely.

        Timeout defaults higher than edge_tts's (8s vs 4s): ElevenLabs'
        highest-quality models render slower than Edge's, and this is the
        backend someone explicitly opted into for quality, so it's worth
        waiting a bit longer before falling back to a lesser-sounding
        voice on a merely-slow (not dead) connection.

        `voice_id`, if given, overrides self.voice_id for this single
        call only - lets a caller (e.g. a future "say this in my dad's
        cloned voice" command) swap voices per-utterance without
        permanently reconfiguring the backend."""
        try:
            resp = requests.post(
                _API_URL.format(voice_id=voice_id or self.voice_id),
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": self.model,
                    "voice_settings": {
                        "stability": self.stability,
                        "similarity_boost": self.similarity_boost,
                    },
                },
                timeout=timeout,
            )
            if resp.status_code != 200:
                # 401 = bad/missing key, 422 = bad voice id, 429 = quota
                # exhausted - all handled the same way (log + fall back)
                # since the fallback chain is the actual recovery path,
                # not a retry here.
                logger.debug("ElevenLabs synth failed (%s): %s", resp.status_code, resp.text[:200])
                return None
            with open(out_path, "wb") as f:
                f.write(resp.content)
            return out_path
        except Exception as e:
            logger.debug("ElevenLabs synth failed, falling back: %s", e)
            return None

    def set_voice(self, voice_id: str):
        self.voice_id = voice_id

    def set_stability(self, stability: float):
        self.stability = max(0.0, min(1.0, stability))

    def set_similarity_boost(self, similarity_boost: float):
        self.similarity_boost = max(0.0, min(1.0, similarity_boost))


def list_voices(api_key: str = ELEVENLABS_API_KEY) -> Optional[list]:
    """List every voice (pretrained + your own cloned ones) available to
    this API key - id, name, category. Returns None on failure rather
    than raising, same soft-fail convention as synthesize()."""
    if not HAS_REQUESTS or not api_key:
        return None
    try:
        resp = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key},
            timeout=8.0,
        )
        if resp.status_code != 200:
            return None
        return [
            {"voice_id": v.get("voice_id"), "name": v.get("name"), "category": v.get("category")}
            for v in resp.json().get("voices", [])
        ]
    except Exception as e:
        logger.debug("ElevenLabs list_voices failed: %s", e)
        return None


def clone_voice(name: str, sample_file_paths: list, api_key: str = ELEVENLABS_API_KEY) -> Optional[str]:
    """Instant-clone a voice from one or more short audio samples
    (clean, minimal background noise, ideally 1-2 min total). Returns
    the new voice_id on success (drop it into ELEVENLABS_VOICE_ID in
    .env), or None on failure."""
    if not HAS_REQUESTS or not api_key:
        return None
    try:
        files = [("files", (p.split("/")[-1], open(p, "rb"), "audio/mpeg")) for p in sample_file_paths]
        resp = requests.post(
            "https://api.elevenlabs.io/v1/voices/add",
            headers={"xi-api-key": api_key},
            data={"name": name},
            files=files,
            timeout=60.0,
        )
        for _, (_, fh, _) in files:
            fh.close()
        if resp.status_code != 200:
            logger.debug("ElevenLabs clone_voice failed (%s): %s", resp.status_code, resp.text[:200])
            return None
        return resp.json().get("voice_id")
    except Exception as e:
        logger.debug("ElevenLabs clone_voice failed: %s", e)
        return None


_instance: Optional[ElevenLabsTTSBackend] = None


def get_elevenlabs_backend() -> ElevenLabsTTSBackend:
    global _instance
    if _instance is None:
        _instance = ElevenLabsTTSBackend()
    return _instance
