"""
Ultron AI Configuration
========================
Central configuration for the Ultron AI assistant.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ---------------------------------------------------------------------------
# Phase 3 - additional FREE-tier LLM providers (ai/llm/). All optional: only
# GROQ_API_KEY is required for Ultron to run at all. ai/llm/model_factory.py
# picks whichever of these is actually configured, in priority order.
# ---------------------------------------------------------------------------
# Full path to tesseract.exe, only needed if the Tesseract-OCR installer
# didn't add it to PATH (common on Windows - default install location is
# C:\Program Files\Tesseract-OCR\tesseract.exe). Leave blank if `tesseract`
# already works from a plain terminal.
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# gemini-1.5-flash and gemini-2.0-flash have both been retired by Google;
# gemini-3.6-flash is the current replacement Google's own 404 response
# points to as of Aug 2026. If a future retirement breaks this again, set
# GEMINI_MODEL in .env to override without touching this file.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# NVIDIA NIM (build.nvidia.com) - OpenAI-compatible endpoint, used as the
# 2nd link in the main tool-calling fallback chain: Groq -> NVIDIA -> Gemini
# -> Ollama (see ai/ai_router.py). Optional: only used if NVIDIA_API_KEY is set.
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

# DeepSeek (api.deepseek.com) - OpenAI-compatible endpoint, optional extra
# fallback link in ai/ai_router.py's cloud chain. Only used if DEEPSEEK_API_KEY
# is set; ai/cloud_models/deepseek_client.py imports these three directly.
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# OpenRouter (openrouter.ai) - OpenAI-compatible endpoint that itself
# multiplexes many free/paid models, optional extra fallback link in
# ai/ai_router.py's cloud chain. Only used if OPENROUTER_API_KEY is set;
# ai/cloud_models/openrouter_client.py imports all six of these directly.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_FALLBACK_MODELS = [m.strip() for m in os.getenv("OPENROUTER_FALLBACK_MODELS", "").split(",") if m.strip()]
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "https://github.com/ultron-assistant")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Ultron")

# xKiro (api.xkiro.com) - OpenAI-compatible AI gateway that itself
# multiplexes 120+ models (OpenAI, Anthropic, DeepSeek, Gemini, etc.) behind
# one key, optional extra fallback link in ai/ai_router.py's cloud chain.
# Only used if XKIRO_API_KEY is set; ai/cloud_models/xkiro_client.py imports
# these three directly. Model IDs are "vendor/model" (e.g. "openai/gpt-5.6-sol")
# - see https://xkiro.com/dashboard for the exact catalog available to your key.
XKIRO_API_KEY = os.getenv("XKIRO_API_KEY")
XKIRO_MODEL = os.getenv("XKIRO_MODEL", "openai/gpt-5.6-sol")
XKIRO_BASE_URL = os.getenv("XKIRO_BASE_URL", "https://api.xkiro.com/v1")

# ---------------------------------------------------------------------------
# Phase 27 - Movie Assistant (modules/movie_assistant/). TMDB (The Movie
# Database) is optional: movie_suggester.py and availability_checker.py
# both work without it (curated static suggestion lists, generic search-
# link fallback for availability) - setting TMDB_API_KEY just switches
# them over to real, current TMDB data (discover-by-genre suggestions,
# the official /watch/providers endpoint for real streaming availability).
# Free to obtain at https://www.themoviedb.org/settings/api - no billing.
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_DEFAULT_COUNTRY = os.getenv("TMDB_DEFAULT_COUNTRY", "IN")

# Preference order ai/llm/model_factory.py tries providers in, comma
# separated. "auto" (default) = groq,gemini,huggingface,ollama.
FREE_MODEL_PRIORITY = os.getenv("FREE_MODEL_PRIORITY", "groq,gemini,huggingface,ollama").strip().lower()

# Which vector DB backend memory/vector_db/ prefers when more than one is
# installed: "auto" (chroma -> faiss -> sqlite), "chroma", "faiss", "sqlite".
VECTOR_DB_BACKEND = os.getenv("VECTOR_DB_BACKEND", "auto").strip().lower()

STORAGE_DIR = BASE_DIR / "storage"
CACHE_DIR = STORAGE_DIR / "cache"
LOGS_DIR = STORAGE_DIR / "logs"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
USAGE_FILE = CACHE_DIR / "ultron_usage.json"


def diagnose_env() -> str:
    """Return a human-readable reason GROQ_API_KEY isn't loading, for the
    startup check in main.py. Only called when the key is missing."""
    if not ENV_PATH.exists():
        maybe_txt = BASE_DIR / ".env.txt"
        if maybe_txt.exists():
            return (
                f"Found '.env.txt' instead of '.env' in {BASE_DIR}. "
                "Windows likely hid the real extension when you saved it. "
                "Rename it to exactly '.env' (enable 'File name extensions' "
                "in File Explorer's View tab to see and fix this)."
            )
        return f"No .env file found at {ENV_PATH}. Create one there with GROQ_API_KEY=your_key_here"

    raw = ENV_PATH.read_text(encoding="utf-8", errors="ignore")
    if "GROQ_API_KEY" not in raw:
        return f".env exists at {ENV_PATH} but has no GROQ_API_KEY line. Add: GROQ_API_KEY=your_key_here"

    return (
        f".env exists at {ENV_PATH} and has a GROQ_API_KEY line, but it didn't load. "
        "Check for extra quotes/spaces around the '=', e.g. it should be "
        "GROQ_API_KEY=gsk_xxx with no quotes and no spaces."
    )


MODEL_NAME = "openai/gpt-oss-120b"
FALLBACK_MODELS = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
]
# BUG FIXED: llama-3.3-70b-versatile and llama-3.1-8b-instant were both
# officially deprecated by Groq (announced 2026-06-17) and fully shut
# down 2026-08-16 - every call to either now 404s as "model unavailable"
# permanently, not a transient rate-limit/outage. Every turn was wasting
# 2 guaranteed-dead attempts (x2 with the router's own retry = 4) before
# ever reaching a model that could actually answer. Replaced with Groq's
# own recommended migration targets: openai/gpt-oss-20b (for
# llama-3.1-8b-instant) and qwen/qwen3.6-27b (for llama-3.3-70b-versatile).
# See https://console.groq.com/docs/deprecations for the current list -
# worth rechecking periodically since Groq deprecates models often.
MAX_TOKENS = 1024
TEMPERATURE = 0.7
TOP_P = 1

# Network timeout/retry settings for the Groq SDK client. Without these the
# underlying httpx client has no timeout at all, so a stalled connection
# (dead wifi, captive portal, ISP hiccup) blocks the call forever - and on
# Windows a blocking socket read can't even be interrupted with Ctrl+C,
# which is what causes the whole terminal to freeze. 20s is generous for a
# single completion call; 2 retries lets transient blips recover without a
# full model-fallback cycle.
GROQ_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", 20))
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", 2))

# How long (seconds) to skip a model after it returns a rate-limit error,
# instead of re-trying it (and re-eating the failure latency) on every
# single turn. See ai/cloud_models/groq_client.py's _MODEL_COOLDOWNS.
MODEL_RATE_LIMIT_COOLDOWN_SECONDS = float(os.getenv("MODEL_RATE_LIMIT_COOLDOWN_SECONDS", 90))

# ---------------------------------------------------------------------------
# Fast-tier model (low-latency pipeline, ai/complexity_router.py) - a small,
# tool-free model used for quick conversational/factual turns so the user
# doesn't wait on MODEL_NAME's full tool-calling loop for a reply that never
# needed a tool in the first place. Kept separate from MODEL_NAME/
# FALLBACK_MODELS above since those are picked for tool-calling reliability;
# this one is picked for raw speed.
# BUG FIXED: llama-3.1-8b-instant (the old default here) was decommissioned
# by Groq on 2026-08-16 - every fast-tier call was silently 404ing and
# falling through to the full chat_with_tools() pipeline every single time,
# defeating the entire point of this tier. openai/gpt-oss-20b is Groq's own
# recommended replacement and is also in FALLBACK_MODELS above.
# NOTE: if your .env sets FAST_MODEL_NAME=llama-3.1-8b-instant explicitly,
# that overrides this default - update the .env value too.
FAST_MODEL_NAME = os.getenv("FAST_MODEL_NAME", "openai/gpt-oss-20b")
try:
    FAST_MODEL_MAX_TOKENS = int(os.getenv("FAST_MODEL_MAX_TOKENS", 300))
except (TypeError, ValueError):
    FAST_MODEL_MAX_TOKENS = 300
try:
    FAST_MODEL_TEMPERATURE = float(os.getenv("FAST_MODEL_TEMPERATURE", 0.6))
except (TypeError, ValueError):
    FAST_MODEL_TEMPERATURE = 0.6

# How many of the most recent conversation_history *entries* (not turns -
# each turn is 2 entries) the fast tier sends along with the user's new
# message. Deliberately much smaller than MAX_HISTORY_LENGTH*2 below (which
# chat_with_tools/the strong model use) - the fast tier exists purely to cut
# latency for quick tool-free turns, and every extra message here is extra
# prompt tokens the model has to read before it can start streaming a reply.
# 6 (3 user/assistant pairs) is enough for the model to track a short
# back-and-forth without meaningfully adding to time-to-first-token.
try:
    FAST_MODEL_HISTORY_MESSAGES = int(os.getenv("FAST_MODEL_HISTORY_MESSAGES", 6))
except (TypeError, ValueError):
    FAST_MODEL_HISTORY_MESSAGES = 6

MAX_HISTORY_LENGTH = 20


# ---------------------------------------------------------------------------
# Voice settings (wake word, TTS, STT) - all overridable via .env so nothing
# below needs code changes to tune for a different mic/voice/accent.
# ---------------------------------------------------------------------------


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Wake word(s) - comma separated in .env, e.g. WAKE_WORDS=ultron,hey ultron
WAKE_WORDS = tuple(w.strip().lower() for w in os.getenv("WAKE_WORDS", "mg").split(",") if w.strip())

# Neural voice for edge-tts. Good options:
#   en-IN-NeerjaNeural  - Indian English, female (default)
#   en-IN-PrabhatNeural - Indian English, male
#   en-US-AvaNeural     - American English, female
#   en-US-GuyNeural     - American English, male
#   en-GB-RyanNeural    - British English, male
TTS_VOICE = os.getenv("TTS_VOICE", "en-IN-NeerjaNeural")

# Hindi-script counterpart, used automatically (voice/tts/tts_engine.py)
# for any sentence that contains Devanagari characters - TTS_VOICE above
# is an *English*-locale voice and either mispronounces or (on some
# edge-tts versions) silently fails to render Devanagari text at all,
# which was the cause of Hindi replies showing on screen but never being
# spoken. hi-IN-SwaraNeural is female, matching TTS_VOICE's default
# gender. hi-IN-MadhurNeural is the male equivalent.
TTS_VOICE_HINDI = os.getenv("TTS_VOICE_HINDI", "hi-IN-SwaraNeural")
TTS_RATE = _env_int("TTS_RATE", 15)  # percent, -50..+100 (speaking speed)
TTS_PITCH = _env_int("TTS_PITCH", 0)  # Hz offset, -50..+50
TTS_VOLUME = _env_int("TTS_VOLUME", 0)  # percent, -50..+50
TTS_CACHE_DIR = CACHE_DIR / "tts_cache"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TTS_CACHE_MAX_CHARS = _env_int("TTS_CACHE_MAX_CHARS", 60)  # only cache short replies

# STT / microphone tuning - lower values = faster turnaround, at the risk of
# cutting off slow talkers. Tuned down from the library defaults for snappier
# back-and-forth conversation.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en-IN")

# Hybrid speech-to-text policy, same shape as AI_MODE below:
#   "auto"  - online -> Google Web Speech API (fast, free, no key);
#             fails/offline -> falls back to local Whisper
#             (voice/stt/local_whisper.py). This is what wake word
#             detection and command transcription both use by default,
#             so voice control keeps working with zero internet.
#   "cloud" - Google only, no fallback (old behavior; errors out offline)
#   "local" - local Whisper only, never touches the network, even when
#             online (fully offline voice pipeline)
STT_MODE = os.getenv("STT_MODE", "auto").strip().lower()

# Local Whisper model size for offline STT - tiny/base/small/medium/large.
# Bigger = more accurate but slower + more RAM. Auto-downloaded from
# Hugging Face and cached under storage/cache/models/whisper/ on first
# use (same lazy-fetch pattern as vision/object_detection.py and
# vision/gestures.py). "base" is a good default on a normal laptop CPU.
WHISPER_LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "base")

MIC_CALIBRATION_SECONDS = _env_float("MIC_CALIBRATION_SECONDS", 0.5)
MIC_PAUSE_THRESHOLD = _env_float("MIC_PAUSE_THRESHOLD", 0.8)  # silence -> phrase end
WAKE_PHRASE_TIME_LIMIT = _env_float("WAKE_PHRASE_TIME_LIMIT", 4.0)
COMMAND_LISTEN_TIMEOUT = _env_float("COMMAND_LISTEN_TIMEOUT", 5.0)
COMMAND_PHRASE_TIME_LIMIT = _env_float("COMMAND_PHRASE_TIME_LIMIT", 15.0)

# ---------------------------------------------------------------------------
# Phase 9 - multi-engine voice stack (voice/wakeword/detector.py,
# voice/stt/{vosk,google,whisper}_stt.py, voice/tts/{pyttsx,gtts,edge}_tts.py,
# voice/audio/processor.py, voice/microphone/stream.py). Every knob below is
# optional - sane free-tier defaults are used if unset, and every engine
# fails soft (falls through to the next one) if its package/model isn't
# installed rather than crashing the voice pipeline.
# ---------------------------------------------------------------------------

# Wake word engine: "openwakeword" (real-time streaming keyword spotter -
# default, low latency, fully offline) or "stt" (legacy rolling-phrase
# approach in voice/wakeword/wakeword.py). Falls back to "stt"
# automatically at runtime if the openwakeword package isn't installed.
WAKE_WORD_ENGINE = os.getenv("WAKE_WORD_ENGINE", "openwakeword").strip().lower()

# Pretrained openwakeword model name(s), comma separated - "hey_ultron"
# ships with the openwakeword package itself (auto-downloaded to its own
# cache on first use). To use a custom-trained wake word instead/as well,
# drop a .onnx or .tflite file into voice/wakeword/models/ and list its
# filename (without extension) here too.
WAKE_WORD_MODELS = tuple(m.strip() for m in os.getenv("WAKE_WORD_MODELS", "hey_ultron").split(",") if m.strip())
WAKE_WORD_MODELS_DIR = BASE_DIR / "voice" / "wakeword" / "models"
WAKE_WORD_MODELS_DIR.mkdir(parents=True, exist_ok=True)
WAKE_WORD_THRESHOLD = _env_float("WAKE_WORD_THRESHOLD", 0.3)
WAKE_WORD_FRAME_MS = _env_int("WAKE_WORD_FRAME_MS", 80)
WAKE_WORD_SMOOTH_FRAMES = _env_int("WAKE_WORD_SMOOTH_FRAMES", 2)
WAKE_WORD_MIC_GAIN = _env_float("WAKE_WORD_MIC_GAIN", 3.0)

# Hybrid speech-to-text policy - same "auto/cloud/local" values as before,
# plus "vosk" for the fully-offline Hindi-capable engine:
#   auto  (default) -> online: Google (voice/stt/google_stt.py); offline or
#                       Google fails -> local Whisper (voice/stt/whisper_stt.py)
#   cloud -> Google only, no fallback
#   local -> local Whisper only, never touches the network
#   vosk  -> local Vosk only, never touches the network - smaller/faster
#            than Whisper and has a dedicated Hindi model
# STT_MODE already existed from Phase 2; STT_LANGUAGE starting with "hi"
# (e.g. "hi-IN") auto-prefers the Hindi Vosk model when STT_MODE == "auto"
# and a Hindi Vosk model is present, since Google/Whisper Hindi accuracy is
# weaker than a language-specific Vosk model.

# Vosk model directories - NOT auto-downloaded (models are 40MB-1GB+ zips
# from https://alphacephei.com/vosk/models). Download and unzip one into
# each path below to enable that language; missing = that language is
# skipped and STT falls through to the next configured engine.
VOSK_MODEL_PATH_EN = os.getenv("VOSK_MODEL_PATH_EN", str(CACHE_DIR / "models" / "vosk" / "en"))
VOSK_MODEL_PATH_HI = os.getenv("VOSK_MODEL_PATH_HI", str(CACHE_DIR / "models" / "vosk" / "hi"))

# Text-to-speech backend - which voice/tts/*_tts.py engine UltronVoice
# synthesizes with:
#   elevenlabs - hyper-realistic / voice-cloned speech, by far the most
#             human-sounding option, needs internet + an API key (opt-in,
#             not the default since it needs setup - see
#             ELEVENLABS_API_KEY below) (voice/tts/elevenlabs_tts.py)
#   edge    (default) - Microsoft Edge neural voices, best quality with
#             zero setup, needs internet (voice/tts/edge_tts.py)
#   gtts    - Google Translate TTS, needs internet, more languages incl.
#             Hindi (voice/tts/gtts_tts.py)
#   pyttsx3 - fully offline, uses the OS's own SAPI5/NSSpeech/espeak voices,
#             lower quality but always works with zero setup and zero
#             internet (voice/tts/pyttsx_tts.py)
# TTS_ENGINE_FALLBACK is tried (in order) if the primary engine's package
# isn't installed, its key/voice isn't configured, or synthesis fails -
# pyttsx3 is last since it's the one guaranteed to work offline. Set
# TTS_ENGINE=elevenlabs once ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID are
# filled in below to make it primary instead of just an available option.
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge").strip().lower()
TTS_ENGINE_FALLBACK = tuple(
    e.strip().lower() for e in os.getenv("TTS_ENGINE_FALLBACK", "edge,gtts,pyttsx3").split(",") if e.strip()
)

# ElevenLabs (voice/tts/elevenlabs_tts.py) - real human-like / cloned
# voice output. Get a free-tier API key at https://elevenlabs.io (Profile
# -> API Keys). ELEVENLABS_VOICE_ID is either one of ElevenLabs' own
# pretrained voices (browse https://elevenlabs.io/app/voice-library) or a
# voice you've cloned yourself from a short audio sample
# (https://elevenlabs.io/app/voice-lab -> Instant Voice Cloning, or
# voice/tts/elevenlabs_tts.py's clone_voice() helper). Left blank by
# default - the backend raises a clear "not configured" error (caught by
# tts_engine.py, which just falls through to TTS_ENGINE_FALLBACK) rather
# than silently misbehaving until both are set.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
# "eleven_multilingual_v2" (default) handles Hindi/English code-switching
# well - matches this project's existing TTS_VOICE_HINDI auto-routing.
# "eleven_turbo_v2" trades a little quality for lower latency if replies
# feel slow to start speaking.
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
# 0.0-1.0: higher = more consistent/monotone, lower = more expressive but
# less predictable. ElevenLabs' own recommended default.
ELEVENLABS_STABILITY = _env_float("ELEVENLABS_STABILITY", 0.5)
# 0.0-1.0: how closely output sticks to the reference voice's timbre -
# higher = closer clone match but can sound slightly less natural.
ELEVENLABS_SIMILARITY_BOOST = _env_float("ELEVENLABS_SIMILARITY_BOOST", 0.75)
GTTS_LANG = os.getenv("GTTS_LANG", "en")  # "hi" for Hindi via gTTS
# Forced gTTS language for any sentence detected as Devanagari script,
# same reasoning as TTS_VOICE_HINDI above - independent of whatever
# GTTS_LANG is set to for everything else, since gTTS renders Devanagari
# input as broken/silent audio under lang="en".
GTTS_LANG_HINDI = "hi"
PYTTSX_VOICE_HINT = os.getenv("PYTTSX_VOICE_HINT", "")  # substring match against OS voice names, e.g. "Zira"

# Startup defaults - "python main.py" with no flags lands here.
VOICE_MODE_DEFAULT = _env_bool("VOICE_MODE_DEFAULT", True)  # hands-free voice on by default
UI_MODE_DEFAULT = _env_bool("UI_MODE_DEFAULT", False)  # orb UI off by default
TEXT_MODE_DEFAULT = _env_bool("TEXT_MODE_DEFAULT", False)  # typed input off by default


# ---------------------------------------------------------------------------
# Hybrid AI (online/offline) settings - see ai/ai_router.py. Everything here
# is overridable via .env so switching local models/hosts never needs a
# code change.
# ---------------------------------------------------------------------------

# "auto" = AIRouter decides per-turn (cloud when online, local when not,
# automatic fallback either way - this is what main.py uses by default).
# Force "cloud" or "local" only for testing/debugging one path in isolation.
AI_MODE = os.getenv("AI_MODE", "auto").strip().lower()

# Local (offline) LLM backend - talks to a locally running Ollama server.
# Not hardcoded: change OLLAMA_MODEL in .env to whatever you've pulled
# (`ollama pull <name>`) without touching any code.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
LOCAL_MAX_TOKENS = _env_int("LOCAL_MAX_TOKENS", 1024)
LOCAL_TEMPERATURE = _env_float("LOCAL_TEMPERATURE", 0.7)
# Caps the KV-cache size Ollama allocates per request. Left unset, Ollama
# sizes the KV cache for the model's full supported context (128K for
# llama3.2), which needs ~14GB of RAM on its own and causes an
# out-of-memory failure on a normal laptop - happens even on a plain "hi"
# with no tools attached, since it's sized before any content arrives.
# 4096 tokens is plenty for a voice/text assistant turn and needs well
# under 1GB. Raise via .env if you have the RAM and want more headroom
# for very long tool results or conversation history.
LOCAL_CONTEXT_LENGTH = _env_int("LOCAL_CONTEXT_LENGTH", 4096)

# Internet connectivity checks (core/internet_monitor.py). Kept short so a
# dead connection is detected quickly, but cached so every single turn
# doesn't pay a network round trip just to check.
INTERNET_CHECK_HOSTS = tuple(
    h.strip() for h in os.getenv("INTERNET_CHECK_HOSTS", "1.1.1.1:53,8.8.8.8:53").split(",") if h.strip()
)
INTERNET_CHECK_TIMEOUT = _env_float("INTERNET_CHECK_TIMEOUT", 1.0)
INTERNET_CHECK_CACHE_SECONDS = _env_float("INTERNET_CHECK_CACHE_SECONDS", 4.0)

# ---------------------------------------------------------------------------
# Latency instrumentation (core/perf_trace.py) - T0-T7 per-turn timestamps
# (wake -> STT -> decision -> AI request -> first output -> first TTS audio
# -> done), logged as one summary line per turn so latency changes can
# actually be measured instead of guessed at. Cheap enough (a few
# time.monotonic() calls + dict writes per turn, no I/O until the one
# summary log line at the end) to leave on by default; turn it off with
# PERF_TRACE_ENABLED=false in .env if the extra log line is unwanted.
PERF_TRACE_ENABLED = _env_bool("PERF_TRACE_ENABLED", True)

# Cloud-call resilience (ai/ai_router.py). One quick retry before the
# router gives up on cloud and falls back to local for this turn.
CLOUD_MAX_RETRIES = _env_int("CLOUD_MAX_RETRIES", 1)
CLOUD_RETRY_BACKOFF_SECONDS = _env_float("CLOUD_RETRY_BACKOFF_SECONDS", 0.6)

# BUG FIXED: OpenRouter/NVIDIA/DeepSeek/xKiro clients (all built on the
# OpenAI SDK) were constructed with no explicit timeout/max_retries, so
# they silently used the SDK's own defaults - a 10-minute timeout and 2
# internal retries with exponential backoff. Combined with ai_router.py's
# own per-backend retry loop, one genuinely slow/hanging provider could
# stall the whole fallback chain for a very long time before ever
# reaching the next backend or local Ollama. Every cloud client now uses
# this short, explicit timeout and disables the SDK's own retry (the
# router + each client's own model-fallback list already handle retrying),
# so a failing backend fails fast and hands off to the next one quickly.
CLOUD_CLIENT_TIMEOUT_SECONDS = _env_float("CLOUD_CLIENT_TIMEOUT_SECONDS", 15.0)

# ---------------------------------------------------------------------------
# Camera + vision skill (skills/vision/, models/vision/model_manager.py).
# Belongs here rather than in a config/vision_config.py submodule: this
# project already has a config/ *directory* (default.yaml etc.), but this
# root-level config.py file is what every module actually imports as
# `config` - a same-named config/ package can't coexist with it (config.py
# always wins the `config` name, so `from config.vision_config import ...`
# is unreachable no matter what's written there). Every other provider's
# settings already live here for the same reason; this follows that.
# ---------------------------------------------------------------------------
CAMERA_DEVICE_INDEX = _env_int("ULTRON_CAMERA_DEVICE_INDEX", 0)
CAMERA_SNAPSHOT_DIR = os.getenv("ULTRON_CAMERA_SNAPSHOT_DIR", "storage/vision_snapshots")
# Auto-exposure/white-balance on most webcams needs a couple of frames to
# settle after the device opens - discard this many before using one.
CAMERA_WARMUP_FRAMES = _env_int("ULTRON_CAMERA_WARMUP_FRAMES", 2)

VISION_MODEL_HOST = os.getenv("VISION_MODEL_HOST", "http://localhost:11434")
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "llava:7b")
VISION_MODEL_TIMEOUT_S = _env_int("VISION_MODEL_TIMEOUT_S", 120)
VISION_DEFAULT_PROMPT = os.getenv(
    "VISION_DEFAULT_PROMPT",
    "Describe what the camera currently sees, in one or two plain sentences.",
)

# Change detection (skills/vision/change_detector.py + vision_memory.py) -
# "did anything change in front of the camera since I last checked".
# Percent of pixels that must differ (after grayscale+blur+threshold diffing)
# between the stored baseline frame and a new frame before it counts as a
# real change, not sensor noise/lighting flicker.
CHANGE_DETECTION_THRESHOLD_PERCENT = _env_float("ULTRON_CHANGE_DETECTION_THRESHOLD_PERCENT", 2.0)
# Rolling JSON memory of the current baseline + recent change events.
# Same storage/cache/*.json convention as installed_apps_cache.json,
# ultron_state.json, etc. - not a new sqlite db, since this is small,
# single-writer, and doesn't need querying.
CHANGE_DETECTION_MEMORY_FILE = os.getenv("ULTRON_CHANGE_DETECTION_MEMORY_FILE", "storage/cache/vision_memory.json")
CHANGE_DETECTION_MAX_EVENTS = _env_int("ULTRON_CHANGE_DETECTION_MAX_EVENTS", 50)
