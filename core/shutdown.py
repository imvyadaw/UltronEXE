"""
Shutdown
========
Graceful shutdown: stops any live voice/wake-word threads and flushes
core.state_manager to disk before the process exits - the mirror image
of core/startup.py. Called from core.assistant.Assistant.handle_command
on the 'exit'/'quit'/'bye' path, and from main.py's outer try/finally so
Ctrl+C and top-level errors also get a clean save instead of just
dying mid-write.

Idempotent and never raises: safe to call more than once (e.g. once
from the 'exit' command path and again from main.py's finally block) -
each step is independently try/excepted and logged, never re-raised, so
one failing step (say, the wake-word detector already stopped) can't
stop state_manager.save() from still running.
"""

from core.logger import get_logger

logger = get_logger("ultron.shutdown")

_shutdown_done = False


def graceful_shutdown(runtime=None) -> None:
    """`runtime` is the core.assistant.Assistant instance, if one was
    constructed - safe to call with None if shutdown happens before
    that (e.g. a startup check failure before the client/processor were
    built)."""
    global _shutdown_done
    if _shutdown_done:
        return
    _shutdown_done = True

    if runtime is not None:
        detector = getattr(runtime, "detector", None)
        if detector is not None:
            try:
                detector.stop()
            except Exception as e:
                logger.warning(f"Error stopping wake-word detector: {e}")

        voice = getattr(runtime, "voice", None)
        if voice is not None:
            try:
                voice.stop()
            except Exception as e:
                logger.warning(f"Error stopping voice: {e}")

    try:
        from core.state_manager import get_state_manager

        get_state_manager().save()
    except Exception as e:
        logger.warning(f"Error saving state on shutdown: {e}")

    logger.info("Ultron shutdown complete.")
