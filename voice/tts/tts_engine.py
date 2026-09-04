"""
Text-to-speech engine (orchestrator)
=======================================
Multi-backend TTS orchestrator (Phase 9). Each concrete engine now lives
in its own module:

    voice/tts/elevenlabs_tts.py - ElevenLabs hyper-realistic / cloned
                                voices (best quality by far, needs
                                internet + API key - opt-in, see
                                config.ELEVENLABS_API_KEY)
    voice/tts/edge_tts.py    - Microsoft Edge neural voices (best quality
                                with zero setup, needs internet) - default
    voice/tts/gtts_tts.py    - Google Translate TTS (needs internet, more
                                languages incl. Hindi)
    voice/tts/pyttsx_tts.py  - OS-native voices via pyttsx3 (offline,
                                always works, lower quality)

config.TTS_ENGINE picks the primary backend; config.TTS_ENGINE_FALLBACK
(default "edge,gtts,pyttsx3") is tried in order if the primary backend's
package isn't installed or a given synthesis call fails - pyttsx3 is last
since it's the one guaranteed to work with zero setup and zero internet.

Speed tricks (unchanged from Phase 2, now backend-agnostic):
  - Sentence chunking: a reply is split into sentences and synthesized one
    at a time. Playback of sentence 1 starts as soon as it's ready instead
    of waiting for the whole reply to render.
  - Prefetching: while sentence N is playing, sentence N+1 is already being
    synthesized in the background.
  - Caching: short, frequently-repeated replies are cached to disk by
    (text, backend, voice-settings) so they play back instantly with no
    network round-trip on repeat. pyttsx3 output (.wav) and edge/gtts
    output (.mp3) are cached side by side, keyed by file extension.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import threading
import queue
import re
from typing import Optional

try:
    import pygame

    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

from config import (
    TTS_ENGINE,
    TTS_ENGINE_FALLBACK,
    TTS_CACHE_DIR,
    TTS_CACHE_MAX_CHARS,
    TTS_VOICE_HINDI,
    GTTS_LANG_HINDI,
)
from voice.tts.lang_detect import is_hindi_script
from core.logger import get_logger

logger = get_logger("tts_engine")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")

# Which file extension each backend's synthesize() produces - used for
# cache filenames and doesn't affect playback (mpv/pygame handle both).
_BACKEND_EXT = {"elevenlabs": "mp3", "edge": "mp3", "gtts": "mp3", "pyttsx3": "wav"}


def split_sentences(text: str):
    """Split a reply into speakable chunks. Falls back to the whole string
    if it doesn't look like multiple sentences."""
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return parts or [text]


def _load_backend(name: str):
    """Instantiate a backend by name, or return None if its package
    isn't installed / it failed to init - never raises."""
    try:
        if name == "elevenlabs":
            from voice.tts.elevenlabs_tts import get_elevenlabs_backend

            return get_elevenlabs_backend()
        if name == "edge":
            from voice.tts.edge_tts import get_edge_backend

            return get_edge_backend()
        if name == "gtts":
            from voice.tts.gtts_tts import get_gtts_backend

            return get_gtts_backend()
        if name == "pyttsx3":
            from voice.tts.pyttsx_tts import get_pyttsx_backend

            return get_pyttsx_backend()
    except Exception as e:
        logger.info("TTS backend '%s' unavailable (%s).", name, e)
        return None
    logger.warning("Unknown TTS backend '%s'.", name)
    return None


class UltronVoice:
    """Voice handler for Ultron - synthesizes via whichever backend(s)
    config.TTS_ENGINE/TTS_ENGINE_FALLBACK resolve to, with sentence
    pipelining, disk caching, and mpv/pygame playback shared across all
    of them."""

    def __init__(self, primary: str = TTS_ENGINE, fallback_order=TTS_ENGINE_FALLBACK):
        # Backend order to try for each sentence: primary first, then
        # the configured fallback chain (primary de-duplicated out of it
        # if it's already first).
        order = [primary] + [b for b in fallback_order if b != primary]
        self._backend_order = order

        self._is_speaking = False
        self._current_process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()

        global HAS_PYGAME
        if HAS_PYGAME:
            try:
                pygame.mixer.init()
            except Exception as e:
                # A4: pygame.mixer.init() raises (e.g. "No available audio
                # device" on headless/server/CI environments, or a driver
                # issue) - this used to be unguarded, which crashed the
                # whole UltronVoice constructor even though mpv-based
                # playback in _play_file() would've worked fine without
                # pygame at all. Downgrade to "no pygame" instead so the
                # mpv path (checked first, per call) still gets a chance,
                # and _play_file() only reports "no player available" if
                # mpv genuinely isn't on PATH either.
                logger.warning("pygame.mixer.init() failed, disabling pygame playback fallback: %s", e)
                HAS_PYGAME = False

    # -- warm-up ---------------------------------------------------------
    def warm_up(self):
        """Touch the primary backend once so its own first-use cost (e.g.
        edge-tts's first network handshake, pyttsx3's engine init) lands
        here instead of on the user's first real reply. Best-effort and
        silent either way - a failed/unavailable backend here is exactly
        what the normal fallback chain in _get_audio_for_sentence()
        already handles at actual speak time, so there's nothing to
        report back to the caller."""
        try:
            self._backend(self._backend_order[0])
        except Exception as e:
            logger.info("TTS warm-up failed for '%s': %s", self._backend_order[0], e)

    # -- backend resolution, cached per name so a package that failed to
    #    import once isn't retried on every single sentence -------------
    _backends_cache = {}

    def _backend(self, name: str):
        if name not in self._backends_cache:
            self._backends_cache[name] = _load_backend(name)
        return self._backends_cache[name]

    # -- caching -------------------------------------------------------
    def _cache_path(self, text: str, backend_name: str, lang_tag: str) -> Optional[str]:
        if len(text) > TTS_CACHE_MAX_CHARS:
            return None
        ext = _BACKEND_EXT.get(backend_name, "mp3")
        key = f"{text}|{backend_name}|{lang_tag}"
        digest = hashlib.md5(key.encode("utf-8")).hexdigest()
        return str(TTS_CACHE_DIR / f"{digest}.{ext}")

    def _get_audio_for_sentence(self, sentence: str) -> Optional[str]:
        """Return a playable audio file path for this sentence, trying
        each configured backend in order until one produces output
        (from cache or fresh synthesis).

        Devanagari-script sentences (see lang_detect.is_hindi_script) are
        routed to TTS_VOICE_HINDI (edge) / GTTS_LANG_HINDI (gtts) instead
        of the default English-India voice/language for this call only -
        without this, a Hindi reply was silently unspeakable: the default
        edge voice is English-locale and either mispronounces or fails to
        render Devanagari, and gTTS was hardcoded to lang="en" regardless
        of the actual text, so both the primary and first fallback backend
        would fail on the same sentence and (depending on what pyttsx3's
        OS voices support) it could go all the way to no audio at all."""
        hindi = is_hindi_script(sentence)
        lang_tag = "hi" if hindi else "default"

        for backend_name in self._backend_order:
            cache_path = self._cache_path(sentence, backend_name, lang_tag)
            if cache_path and os.path.exists(cache_path):
                return cache_path

            backend = self._backend(backend_name)
            if backend is None:
                continue

            target = (
                cache_path
                or tempfile.NamedTemporaryFile(suffix=f".{_BACKEND_EXT.get(backend_name, 'mp3')}", delete=False).name
            )

            kwargs = {}
            if hindi and backend_name == "edge":
                kwargs["voice"] = TTS_VOICE_HINDI
            elif hindi and backend_name == "gtts":
                kwargs["lang"] = GTTS_LANG_HINDI

            result = backend.synthesize(sentence, target, **kwargs)
            if result:
                return result
            logger.info("Backend '%s' failed to synthesize - trying next fallback.", backend_name)
        return None

    # -- public API ----------------------------------------------------
    def speak(self, text: str, blocking: bool = True):
        if not text or not text.strip():
            return

        self._stop_event.clear()

        if blocking:
            self._speak_streaming(text)
        else:
            thread = threading.Thread(target=self._speak_streaming, args=(text,), daemon=True)
            thread.start()

    def _speak_streaming(self, text: str):
        """Sentence-pipelined playback: sentence 1 starts playing while
        sentence 2 is still being synthesized in the background."""
        try:
            self._is_speaking = True
            sentences = split_sentences(text)
            if not sentences:
                return

            audio_q: "queue.Queue" = queue.Queue(maxsize=2)
            SENTINEL = object()

            def producer():
                for sentence in sentences:
                    if self._stop_event.is_set():
                        break
                    path = self._get_audio_for_sentence(sentence)
                    audio_q.put(path)
                audio_q.put(SENTINEL)

            producer_thread = threading.Thread(target=producer, daemon=True)
            producer_thread.start()

            while True:
                if self._stop_event.is_set():
                    break
                item = audio_q.get()
                if item is SENTINEL:
                    break
                if item is None:
                    continue
                self._play_file(item)

        except Exception as e:
            print(f"Voice error: {e}")
        finally:
            self._is_speaking = False
            self._current_process = None

    def _play_file(self, path: str):
        """Play a single rendered audio file, preferring mpv (lower
        overhead) and falling back to pygame."""
        if self._stop_event.is_set():
            return

        try:
            from core.perf_trace import mark

            mark("T6_first_audio")  # no-ops after the first call per turn
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.tts.tts_engine._play_file")

        if shutil.which("mpv"):
            try:
                self._current_process = subprocess.Popen(
                    ["mpv", "--no-video", "--really-quiet", "--no-terminal", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._current_process.wait()
                return
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("voice.tts.tts_engine._play_file")

        if not HAS_PYGAME:
            print("Voice error: neither mpv nor pygame available to play audio")
            return

        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if self._stop_event.is_set():
                    pygame.mixer.music.stop()
                    break
                pygame.time.Clock().tick(15)
        finally:
            try:
                pygame.mixer.music.unload()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("voice.tts.tts_engine._play_file")

    def speak_stream(self, text_chunks, blocking: bool = True) -> str:
        """Speak an LLM reply as it streams in, instead of waiting for the
        whole string like speak() needs. `text_chunks` is any iterable of
        text deltas (a generator is the normal case - see
        ai.cloud_models.groq_client.chat_fast_stream). Chunks are buffered
        until a full sentence appears (same _SENTENCE_SPLIT_RE boundary
        speak() uses), and each finished sentence is handed to the same
        _get_audio_for_sentence()/_play_file() pipeline speak() uses -
        sentence 1 can start playing while the model is still generating
        sentence 3, on top of the sentence-ahead prefetch that pipeline
        already does.

        Returns the full accumulated text once streaming finishes (or is
        stopped). With blocking=False this returns "" immediately instead
        (the background thread still speaks, but there's no result left to
        hand back synchronously) - callers that need the full text back
        (core.assistant._handle_fast_tier does) should use the default
        blocking=True, same as speak() callers who need the call to have
        actually finished before moving on.
        """
        self._stop_event.clear()

        if not blocking:
            thread = threading.Thread(target=self._speak_stream_sync, args=(text_chunks,), daemon=True)
            thread.start()
            return ""

        return self._speak_stream_sync(text_chunks)

    def _speak_stream_sync(self, text_chunks) -> str:
        self._is_speaking = True
        audio_q: "queue.Queue" = queue.Queue(maxsize=2)
        SENTINEL = object()
        full_text = []

        def producer():
            buffer = ""
            try:
                try:
                    for chunk in text_chunks:
                        if self._stop_event.is_set():
                            return
                        if not chunk:
                            continue
                        full_text.append(chunk)
                        buffer += chunk
                        while True:
                            m = _SENTENCE_SPLIT_RE.search(buffer)
                            if not m:
                                break
                            sentence, buffer = buffer[: m.start()].strip(), buffer[m.end() :]
                            if sentence and not self._stop_event.is_set():
                                audio_q.put(self._get_audio_for_sentence(sentence))
                except Exception as e:
                    # A stream that dies partway (network drop, upstream
                    # error) still leaves whatever trailing partial
                    # sentence was buffered - flush it below the same as
                    # a clean finish, instead of silently swallowing the
                    # last fragment the user's already-printed reply
                    # includes.
                    logger.info("speak_stream producer error: %s", e)
                tail = buffer.strip()
                if tail and not self._stop_event.is_set():
                    audio_q.put(self._get_audio_for_sentence(tail))
            finally:
                audio_q.put(SENTINEL)

        producer_thread = threading.Thread(target=producer, daemon=True)
        producer_thread.start()

        try:
            while True:
                if self._stop_event.is_set():
                    break
                item = audio_q.get()
                if item is SENTINEL:
                    break
                if item is None:
                    continue
                self._play_file(item)
        except Exception as e:
            print(f"Voice error: {e}")
        finally:
            self._is_speaking = False
            self._current_process = None

        return "".join(full_text)

    def stop(self):
        """Interrupt whatever is currently being spoken (used by the
        'stop'/'cancel' voice command)."""
        self._stop_event.set()
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("voice.tts.tts_engine.stop")
        if HAS_PYGAME:
            try:
                pygame.mixer.music.stop()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("voice.tts.tts_engine.stop")
        try:
            for backend in self._backends_cache.values():
                if backend is not None and hasattr(backend, "stop"):
                    backend.stop()
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.tts.tts_engine.stop")
        try:
            subprocess.run(["taskkill", "/IM", "mpv.exe", "/F"], capture_output=True, timeout=10)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("voice.tts.tts_engine.stop")

    def is_speaking(self) -> bool:
        return self._is_speaking

    def set_voice(self, voice: str):
        """Forwards to the primary backend if it supports it (currently
        just edge_tts.py, which has named neural voices)."""
        backend = self._backend(self._backend_order[0])
        if backend is not None and hasattr(backend, "set_voice"):
            backend.set_voice(voice)

    def set_rate(self, rate_percent: int):
        backend = self._backend(self._backend_order[0])
        if backend is not None and hasattr(backend, "set_rate"):
            backend.set_rate(rate_percent)

    def set_pitch(self, pitch_hz: int):
        backend = self._backend(self._backend_order[0])
        if backend is not None and hasattr(backend, "set_pitch"):
            backend.set_pitch(pitch_hz)

    def set_volume(self, volume_percent: int):
        backend = self._backend(self._backend_order[0])
        if backend is not None and hasattr(backend, "set_volume"):
            backend.set_volume(volume_percent)

    def set_engine(self, name: str):
        """Switch the primary TTS backend at runtime, e.g. "pyttsx3" to
        force fully-offline speech. Keeps the same fallback chain after
        it, minus the new primary if it was already in there."""
        name = name.strip().lower()
        order = [name] + [b for b in self._backend_order if b != name]
        self._backend_order = order


_voice_instance: Optional[UltronVoice] = None


def get_voice() -> UltronVoice:
    global _voice_instance
    if _voice_instance is None:
        _voice_instance = UltronVoice()
    return _voice_instance


def speak(text: str, blocking: bool = True):
    get_voice().speak(text, blocking)


async def list_voices():
    """List all available Edge TTS voices (edge-tts specific - kept here
    for backward compat since callers used to import this from
    tts_engine.py directly)."""
    from voice.tts.edge_tts import list_voices as _edge_list_voices

    return await _edge_list_voices()
