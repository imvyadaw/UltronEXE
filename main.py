"""
ULTRON - Your Personal AI Assistant
================================================
Your personal AI assistant powered by Groq with system control and voice.

Usage:
    python main.py            # Default: hands-free voice mode.
                               # Say 'Ultron', wait for the chime/prompt,
                               # then speak your command. Wake word is
                               # always listening. Text input and the
                               # orb UI are OFF until you ask for them:
                               #   say "UI mode on"    -> shows the voice orb
                               #   say "text mode on"  -> also accepts typed input
                               #   say "silent mode on"-> replies in text only
                               #   say "dashboard on"  -> opens the live web dashboard
                               #   say "auto mode on"  -> non-destructive actions run
                               #                          without asking (destructive
                               #                          ones still always confirm)
                               #   say "stop"/"cancel" -> interrupts speech
    python main.py --text     # Text-only mode (no mic, no voice output)
    python main.py --voice    # Typed input, spoken output (legacy)
    python main.py --ui       # Also open the voice orb + tray icon at startup
"""

import sys
import os
import signal
import argparse
import logging
import warnings


def _install_force_exit_safety_net():
    """Second Ctrl+C forces an immediate hard exit.

    Root-cause network hangs (Groq client, Google STT, etc.) now all carry
    real timeouts, so a normal Ctrl+C should break out of the current call
    cleanly on its own. This is only a last-resort backstop for anything
    that isn't covered - e.g. a third-party library making its own
    unguarded blocking call deep in the stack, where a *single* Ctrl+C
    can't reach the code that would raise KeyboardInterrupt in a place
    Python can act on it. A second Ctrl+C within 3s of the first calls
    os._exit(1) directly, skipping normal interpreter shutdown, which is
    the only thing guaranteed to actually kill a wedged process on
    Windows.
    """
    state = {"last_press": 0.0}

    def handler(signum, frame):
        import time

        now = time.monotonic()
        if now - state["last_press"] < 3.0:
            print("\nForce exiting...")
            os._exit(1)
        state["last_press"] = now
        # Let the default KeyboardInterrupt path run as normal for the
        # first press.
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, handler)
    except (ValueError, OSError):
        from core.error_trace import log_swallowed as _lsw

        _lsw("main._install_force_exit_safety_net")


_install_force_exit_safety_net()

warnings.filterwarnings("ignore", message="Revert to STA COM threading mode")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from core.brain import get_brain
from core.startup import run_startup_checks
from core.warmup import warm_up_async
from core.shutdown import graceful_shutdown
from core.assistant import Assistant as UltronRuntime, C
from skills.ai.commands import get_command_processor


def banner():
    print(f"""
{C.BLUE}{C.BOLD}
    +===================================================================+
    |        JJJ  AAAAA  RRRR   V   V  III  SSSS                        |
    |         J   A   A  R   R  V   V   I   S                           |
    |         J   AAAAA  RRRR    V V    I   SSSS                        |
    |    J    J   A   A  R  R    V V    I       S                       |
    |    JJJJJ    A   A  R   R    V    III  SSSS                        |
    |                                                                   |
    |               Your Personal AI Assistant                          |
    +===================================================================+
{C.RESET}""")


def _start_ui():
    """Best-effort: start the tray icon at launch (--ui flag). Never
    raises - if pystray/Pillow aren't available, Ultron just runs the
    same as without --ui, with a console warning explaining what to
    install. The voice orb itself is opened separately (see
    UltronRuntime.enable_ui), since it can also be toggled at runtime by
    voice command."""
    try:
        from ui.tray.tray import get_tray

        tray = get_tray()
        if tray:
            tray.start()
            print(f"{C.CYAN}Tray icon active.{C.RESET}")
        else:
            print(f"{C.YELLOW}Tray icon skipped: run 'pip install pystray Pillow' to enable it.{C.RESET}")
    except Exception as e:
        print(f"{C.YELLOW}Tray icon unavailable: {e}{C.RESET}")


def main():
    parser = argparse.ArgumentParser(description="ULTRON AI Assistant")
    parser.add_argument("--text", action="store_true", help="Text-only mode: no microphone, no voice output")
    parser.add_argument("--voice", action="store_true", help="Legacy voice mode: typed input, spoken output")
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Hands-free voice mode (this is the default when no flags are "
        "given - kept as an explicit flag for scripts/shortcuts)",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Also open the voice orb + system tray icon at startup "
        '(you can also say "UI mode on" at any time instead)',
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Also open the live web dashboard (CPU/RAM + real-time "
        "conversation feed) at startup in your browser "
        '(you can also say "dashboard on" at any time instead)',
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Skip the assistant entirely and drop into core.debug_console " "(after running startup checks)",
    )
    args = parser.parse_args()

    banner()
    run_startup_checks()
    if not args.text and not args.debug:
        warm_up_async()

    if args.debug:
        from core.debug_console import run as run_debug_console

        run_debug_console()
        return

    if args.ui:
        _start_ui()

    runtime = None
    try:
        client = get_brain()
        processor = get_command_processor()
        runtime = UltronRuntime(client, processor)

        # P1: Mission Persistence Engine auto-resume - surface any mission
        # left open from a previous session right away instead of the user
        # having to remember to ask "what was I working on".
        if getattr(runtime, "mission_startup_brief", None):
            print(f"{C.YELLOW}{runtime.mission_startup_brief}{C.RESET}")

        if args.ui:
            runtime.enable_ui()

        if args.dashboard:
            runtime.open_dashboard()

        if args.text:
            runtime.run_text()
        elif args.voice:
            runtime.run_voice_typed()
        else:

            runtime.run_listen()

    except ValueError as e:
        print(f"{C.RED}Config Error: {e}{C.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{C.RED}Error: {e}{C.RESET}")
        sys.exit(1)
    finally:
        graceful_shutdown(runtime)


if __name__ == "__main__":
    main()
