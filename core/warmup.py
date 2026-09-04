"""
Startup warm-up
================
Preloads whatever is genuinely slow on its *first* real use, in a
background daemon thread, so that cost lands during Ultron's own
startup window instead of on the user's first wake word / command.
Never blocks main.py's boot (fire-and-forget thread, started right
after run_startup_checks() and before the wake-word loop begins), and
never raises into it - every item warmed here is independently guarded
so one failing warm-up (missing optional package, no mic, no model
file on disk) can't stop the others from running.

What's actually worth warming here, and why:
  - TTS: voice.tts.tts_engine.get_voice() is a process-wide singleton
    (pygame.mixer.init() happens in its __init__), and UltronVoice.
    warm_up() additionally touches the configured backend client
    (edge-tts/gtts/pyttsx3) so *that* first-use cost (network
    handshake, engine init) also lands here - the later run_listen()
    call to get_voice() is then instant, it just returns the already-
    built singleton.
  - pywinauto: importing it runs a one-time COM threading-mode init
    (the "Revert to STA COM threading mode" warning main.py already
    silences comes from this). One-time cost, one-time warm.
  - Local STT model(s): voice/stt/whisper_stt.py's own comment calls
    out that loading the model "takes a couple [of seconds]" - and
    both it and voice/stt/vosk_stt.py memoize the loaded model in a
    module-level dict, so triggering that load here means the first
    real transcribe_audio() call downstream doesn't pay it. Mirrors
    voice/stt/stt_engine.py's own STT_MODE policy (see its module
    docstring) closely enough to know which local model(s) are
    actually reachable - no point loading Whisper's model if
    STT_MODE would never fall back to it.
  - windows.apps.manager's on-disk installed-apps cache: NOT a
    singleton (skills/app_control/*.py and windows/__init__.py each
    construct their own AppManager()), so warming this doesn't help
    any particular in-memory instance - but it does mean that if this
    is a fresh install (or the daily cache TTL just expired), the
    expensive part - a full recursive Start Menu .rglob() scan - has
    already happened and been written to disk before a real "open
    <app>" command needs it, instead of that first command paying for
    the scan itself. A throwaway AppManager() instance is used and
    discarded; every other call site still reads the (now-warm)
    on-disk cache exactly as it already did before this existed.

Deliberately NOT warmed here:
  - The Groq client - already constructed synchronously in main.py
    right after run_startup_checks(), before this thread would even
    get much of a head start, and construction itself is cheap (no
    network call happens until the first real chat/completion call).
  - ai/complexity_router.py's regex - already compiled once at import
    time as a module-level constant; nothing left to warm.
  - windows.apps.manager.AppManager() itself as a reusable instance -
    see above; only its on-disk cache file is worth pre-populating.
"""

import threading

from config import STT_MODE, STT_LANGUAGE
from core.logger import get_logger

logger = get_logger("ultron.warmup")


def _warm_tts():
    try:
        from voice.tts.tts_engine import get_voice

        get_voice().warm_up()
    except Exception as e:
        logger.info("TTS warm-up skipped: %s", e)


def _warm_pywinauto():
    try:
        import pywinauto  # noqa: F401 - the import itself is the warm-up
    except Exception as e:
        logger.info("pywinauto warm-up skipped: %s", e)


def _warm_stt():
    try:
        if STT_MODE == "vosk":
            from voice.stt import vosk_stt

            vosk_stt._get_model(STT_LANGUAGE)
        elif STT_MODE == "local":
            from voice.stt import whisper_stt

            whisper_stt._get_model()
        elif STT_MODE == "auto":
            # auto's actual pick at call time depends on language +
            # online state. Vosk-Hindi is warmed unconditionally when the
            # configured language is Hindi, because stt_engine.py's policy
            # picks it as the *primary* engine then (not just an offline
            # fallback) - it's genuinely about to be used every turn.
            #
            # Whisper, by contrast, is purely an offline safety net in
            # auto mode (only reached if Google STT fails or there's no
            # internet) - loading it unconditionally at every boot meant
            # every online session paid Whisper's RAM/load cost for a
            # fallback path it would likely never take this run. Only
            # warm it here if we're actually offline right now; otherwise
            # leave it to whisper_stt.py's own memoized first-use load,
            # which pays that cost once, only if/when a real turn ever
            # needs it.
            from voice.stt import vosk_stt

            try:
                vosk_stt._get_model(STT_LANGUAGE)
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("core.warmup._warm_stt")
            try:
                from core.internet_monitor import is_online

                if not is_online():
                    from voice.stt import whisper_stt

                    whisper_stt._get_model()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("core.warmup._warm_stt.whisper_offline_check")
        # "cloud" mode only ever uses Google STT (no local model to
        # preload) - nothing to warm for it here.
    except Exception as e:
        logger.info("STT warm-up skipped: %s", e)


def _warm_app_cache():
    try:
        from windows.apps.manager import AppManager

        AppManager().get_installed_apps()
    except Exception as e:
        logger.info("App cache warm-up skipped: %s", e)


def _run_background_startup_checks():
    """Speed fix: core/startup.py's internet + intelligence_layer
    checks used to block main.py before the assistant could respond to
    anything (up to ~2s+ for the internet check alone on networks where
    the raw socket connect is slow - see core/internet_monitor.py).
    Both already "degrade, don't crash" on their own, so they only need
    to happen eventually, not before boot - same reasoning as every
    other step in this file."""
    try:
        from core.startup import run_background_checks, print_report

        report = run_background_checks()
        print_report(report)
    except Exception as e:
        logger.info("Background startup checks skipped: %s", e)


_WARM_STEPS = (_warm_tts, _warm_pywinauto, _warm_stt, _warm_app_cache, _run_background_startup_checks)


def _run():
    for step in _WARM_STEPS:
        try:
            step()
        except Exception as e:
            # Belt-and-braces - each step already guards itself, this
            # just ensures one truly unexpected failure can't stop the
            # rest of the list from still running.
            logger.info("Warm-up step '%s' failed, continuing: %s", step.__name__, e)
    logger.info("Background warm-up finished.")


def warm_up_async() -> threading.Thread:
    """Fire-and-forget: spawns the background warm-up thread and
    returns immediately without waiting for it. Call once, right after
    run_startup_checks() and before the wake-word loop starts - calling
    it again would just spawn a redundant second thread doing the same
    (harmless but pointless) work."""
    thread = threading.Thread(target=_run, daemon=True, name="ultron-warmup")
    thread.start()
    return thread
