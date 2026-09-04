"""
MCP Server for ULTRON
======================
Exposes the existing Ultron Assistant (core/assistant.py) as an MCP
server so any MCP client (Claude Desktop, Claude Code, Cursor, etc.)
can send it commands over stdio and get back whatever Ultron's normal
6-tier routing pipeline would have said.

This does NOT reimplement Ultron - it boots the exact same
client/processor/Assistant stack main.py boots (minus voice/mic, which
has no meaning for a headless MCP subprocess), then feeds each MCP
tool call straight into Assistant.handle_command(), the same single
entry point main.py's run_text()/run_voice_typed()/run_listen() all
use. Every one of Ultron's internal tools, its memory, its
intelligence layer, autonomy, etc. all stay reachable exactly as
before - MCP just becomes one more caller of handle_command(), same
as typed text input.

IMPORTANT stdio-transport constraint: MCP over stdio uses stdin/stdout
for the JSON-RPC protocol itself. Ultron's own code prints straight to
stdout in several places (banner, the fast-tier streaming path,
_route_turn's "ULTRON: ..." lines, tool-call echoes) - if any of that
leaked onto real stdout while an MCP client is attached, it would
corrupt the protocol stream and silently break the connection. Every
call into Ultron below runs inside a `contextlib.redirect_stdout`
block, capturing anything Ultron prints into a buffer that only ever
goes to the log file (via logger, which is file-based - see
core/logger.py) or stderr, never back out through real stdout.

Setup:
    pip install "mcp>=1.2.0,<2"
    (Ultron's own requirements.txt / requirements-windows.txt already
    cover everything else this needs - client/brain, command
    processor, memory, etc. Voice/STT packages are never imported by
    this server, so the faster_whisper/torch DLL issue noted in
    ULTRON_VOICE_MODE_FIX_GUIDE.md cannot affect it.)

Run directly for a local stdio server:
    python mcp_server.py

Or point an MCP client at this file - see README_MCP.md for exact
Claude Desktop / Claude Code config.
"""

from __future__ import annotations

import contextlib
import io
import sys
import threading
from pathlib import Path

# Make the project root importable regardless of the CWD the MCP client
# launches this from (Claude Desktop launches subprocesses with an
# arbitrary/unpredictable working directory).
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover - startup guidance only
    raise SystemExit(
        "The 'mcp' package isn't installed. Run:\n"
        '    pip install "mcp>=1.2.0,<2"\n'
        "(pin below 2.0 - the v2 API renamed FastMCP to MCPServer and this "
        "server uses the v1 API)."
    ) from e

from core.logger import get_logger

logger = get_logger("ultron.mcp_server")

mcp = FastMCP("ultron")

# Turns that must never reach Assistant.handle_command() as-is: that
# method's tier-0 exit path (core/assistant.py's _route_turn) calls
# sys.exit(0) directly on "exit"/"quit"/"bye", which would kill this
# MCP server process, not just "end the conversation" the way it does
# in main.py's own run_text()/run_listen() loops.
_PROCESS_EXIT_PHRASES = {"exit", "quit", "bye"}

# One Assistant instance for the life of this server process, built
# lazily on the first tool call (not at import time) so MCP capability
# negotiation and client introspection never pay Ultron's full boot
# cost, and a client that never actually sends a command never pays it
# either. Guarded by a lock since FastMCP can dispatch tool calls
# concurrently.
_assistant = None
_assistant_lock = threading.Lock()


def _get_assistant():
    global _assistant
    if _assistant is not None:
        return _assistant
    with _assistant_lock:
        if _assistant is not None:
            return _assistant
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            from core.startup import run_startup_checks
            from core.brain import get_brain
            from skills.ai.commands import get_command_processor
            from core.assistant import Assistant

            # Same checks main.py runs before constructing Assistant.
            # warm_up_async() is deliberately skipped here - it
            # preloads TTS/local-STT models this headless server never
            # uses (no mic/speaker in an MCP subprocess), including the
            # faster_whisper path already flagged as fragile on
            # Windows in ULTRON_VOICE_MODE_FIX_GUIDE.md.
            run_startup_checks()
            client = get_brain()
            processor = get_command_processor()
            assistant = Assistant(client, processor)
            # self.voice is already None until a run_*/enable_ui() call
            # sets it up, so speak_reply() is already a no-op - but set
            # silent_mode too, defensively, in case any future code
            # path wires voice some other way.
            assistant.silent_mode = True
            _assistant = assistant
        logged = buf.getvalue().strip()
        if logged:
            logger.info("[mcp_server] Ultron startup output (kept out of stdout):\n%s", logged)
    return _assistant


def _run_ultron_command(text: str) -> str:
    """Feed `text` into Assistant.handle_command() and capture whatever
    it emits on the 'response_ready' event bus - the same event
    ui/web_dashboard's SSE stream and speak_reply() both already
    subscribe to (see core/assistant.py's _route_turn). EventBus.emit()
    (core/events.py) calls subscribers synchronously and in-process, so
    by the time handle_command() returns, every response_ready this
    turn produced has already landed in `captured`.

    A single turn can legitimately emit response_ready more than once
    (e.g. a fast-tier stream emits its own before any fallback tier
    would run) - these are joined in order rather than keeping only
    the first/last, since a fallback's text is a real part of what
    Ultron "said" for that turn.
    """
    from core.events import get_event_bus

    assistant = _get_assistant()
    bus = get_event_bus()

    captured: list[str] = []

    def _capture(text: str = "", **kwargs):
        if text:
            captured.append(text)

    # core/events.py's EventBus has no unsubscribe - handlers accumulate
    # for the life of the process. Harmless here since this server only
    # ever drives handle_command() through this one function, but noted
    # so a future refactor doesn't assume subscribe/unsubscribe symmetry.
    bus.subscribe("response_ready", _capture)

    stdout_buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout_buf):
            assistant.handle_command(text)
    except SystemExit:
        # Should be unreachable given the exit-phrase guard in
        # ultron_command() below, but never let a stray sys.exit() from
        # deep in Ultron's pipeline actually kill this MCP server.
        logger.exception("[mcp_server] handle_command attempted to exit the process for input: %r", text)
        return "Ultron tried to shut down for that command - ignored so the MCP server keeps running."
    except Exception:
        logger.exception("[mcp_server] handle_command failed for input: %r", text)
        return "Ultron hit an internal error handling that command - check logs/ultron.log for details."
    finally:
        logged = stdout_buf.getvalue().strip()
        if logged:
            logger.info("[mcp_server] Ultron console output (kept out of stdout):\n%s", logged)

    if not captured:
        return (
            "(No text reply for that turn - it was likely a silent control "
            'command, e.g. a mode toggle like "ui mode on".)'
        )
    return "\n\n".join(captured)


@mcp.tool()
def ultron_command(text: str) -> str:
    """Send a command or question to Ultron exactly as if you'd typed it
    into Ultron's own text mode. Runs through Ultron's full pipeline -
    tool calls (apps, browser, files, calendar, contacts, social,
    system control, etc.), memory (episodic/semantic/procedural), the
    intelligence layer, and slash-commands - and returns whatever
    Ultron would have said back.

    Examples: "cpu kitna use ho raha hai", "open chrome",
    "remind me to call mom at 6pm", "what's on my calendar tomorrow".
    """
    if not text or not text.strip():
        return "Give me something to say to Ultron first."
    cleaned = text.strip()
    if cleaned.lower() in _PROCESS_EXIT_PHRASES:
        return "Not running that here - it would shut down the MCP server " "process itself, not just end a chat turn."
    return _run_ultron_command(cleaned)


@mcp.tool()
def ultron_reset() -> str:
    """Clear Ultron's conversation history for this session (same as the
    '/reset' or '/clear' slash-command, or saying "reset conversation"
    to Ultron directly)."""
    assistant = _get_assistant()
    stdout_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf):
        assistant.client.clear_history()
    return "Ultron's conversation history has been cleared."


@mcp.tool()
def ultron_status() -> str:
    """Report which of Ultron's optional subsystems are actually
    connected in this MCP server process (intelligence layer, Phase 18
    observer layer / consciousness+personality). Useful for confirming
    the server booted the full stack rather than a degraded one."""
    assistant = _get_assistant()
    lines = [
        f"Intelligence layer: {'connected' if assistant.intelligence is not None else 'unavailable'}",
        f"Consciousness/personality layer: {'connected' if assistant.consciousness is not None else 'unavailable'}",
        "Voice: not applicable - this MCP server runs headless (text in, text out only)",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
