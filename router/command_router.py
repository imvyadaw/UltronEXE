"""
router.command_router
======================
Single entry point for the three "does this ever reach the LLM at all"
checks that core.assistant.Assistant.handle_command runs as its first
three steps: control commands (mode toggles / stop), slash commands
(/help, /reset, ...), and unambiguous local system commands
(time/date/volume/open app/...). Front-ends other than the main CLI
loop - a Telegram/WhatsApp plugin, core.debug_console's `route` command
- can call route_command() once instead of re-implementing that
three-step fallthrough themselves.

core.assistant.Assistant keeps its own inline version rather than
switching to this, since it also needs to *apply* control actions to
itself (self.enable_ui(), self.disable_text_mode(), ...) - this module
only reports what matched, decoupled from any particular runtime
object, and leaves applying the action up to the caller.
"""

from dataclasses import dataclass
from typing import Optional

from ai import local_router


@dataclass
class CommandRouteResult:
    handled: bool
    kind: Optional[str] = None  # "control" | "slash" | "system" | None
    action: Optional[str] = None  # control action name, if kind == "control"
    response: Optional[str] = None  # text reply, if any


def route_command(text: str, processor=None) -> CommandRouteResult:
    """Try control commands, then slash commands (if a CommandProcessor
    is given), then unambiguous local system commands, in that order -
    the same order core.assistant.Assistant.handle_command uses.
    Returns handled=False if nothing matched, meaning the caller should
    fall through to router.intent_router / the LLM.

    `processor` is a skills.ai.commands.CommandProcessor instance -
    optional because not every caller (e.g. core.debug_console) has one
    handy, and slash commands are meaningless without it anyway.
    """
    action = local_router.check_control_command(text)
    if action:
        return CommandRouteResult(handled=True, kind="control", action=action)

    if processor is not None:
        is_cmd, cmd_response = processor.process(text)
        if is_cmd:
            return CommandRouteResult(handled=True, kind="slash", response=cmd_response)

    local_result = local_router.route_system_command(text)
    if local_result and local_result.handled_locally:
        return CommandRouteResult(handled=True, kind="system", response=local_result.response)

    return CommandRouteResult(handled=False)
