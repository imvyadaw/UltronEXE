"""
remote_controller.py
====================
Lets a paired device ask the ULTRON host to do something ("pause
music", "read me my next event", "lock screen") - and nothing more
than that. Same pattern as SELF_HEALING.auto_recovery from Phase
17.7: a command only runs if you've explicitly registered a callback
for its exact name via `register_command()`. There is no generic
"run this shell command" or "open this path" escape hatch - if a
capability isn't registered, the request is rejected, logged, and
that's the end of it.

Every invocation is authorized against the requesting device's
granted command set (set via `grant()`), so pairing a device doesn't
by itself hand it every registered command - you decide per device.

Pure standard library.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ultron.remote_controller")

DEFAULT_LOG_PATH = "ultron_data/cross_device/remote_command_log.json"
MAX_LOG_ENTRIES = 500


@dataclass
class CommandResult:
    command: str
    device_id: str
    ok: bool
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class RemoteController:
    """Dispatches whitelisted remote commands from paired devices to
    locally-registered callbacks. Never executes arbitrary code."""

    def __init__(self, log_path: str = DEFAULT_LOG_PATH):
        self.log_path = log_path
        self._commands: Dict[str, Callable[[dict], Any]] = {}
        self._grants: Dict[str, set] = {}  # device_id -> set of command names
        self._log: List[dict] = []
        self._load_log()

    def register_command(self, name: str, handler: Callable[[dict], Any]) -> None:
        """Register what a command actually does, e.g.
        `register_command("music.pause", lambda args: media_player.pause())`."""
        self._commands[name] = handler
        logger.info("Registered remote command '%s'", name)

    def grant(self, device_id: str, command_names: List[str]) -> None:
        """Allow a specific device to invoke a specific set of commands."""
        self._grants[device_id] = set(command_names)
        logger.info("Granted device %s commands: %s", device_id, command_names)

    def revoke_all(self, device_id: str) -> None:
        self._grants.pop(device_id, None)

    def available_commands(self) -> List[str]:
        return sorted(self._commands.keys())

    def granted_commands(self, device_id: str) -> List[str]:
        return sorted(self._grants.get(device_id, set()))

    def execute(self, device_id: str, command: str, args: Optional[dict] = None) -> CommandResult:
        args = args or {}

        if command not in self._commands:
            result = CommandResult(command, device_id, ok=False, detail="unknown command")
        elif command not in self._grants.get(device_id, set()):
            logger.warning("Device %s attempted ungranted command '%s'", device_id, command)
            result = CommandResult(command, device_id, ok=False, detail="not granted")
        else:
            try:
                out = self._commands[command](args)
                result = CommandResult(command, device_id, ok=True, detail=str(out) if out is not None else "")
            except Exception as exc:
                logger.exception("Command '%s' raised", command)
                result = CommandResult(command, device_id, ok=False, detail=f"error: {exc}")

        self._append_log(result)
        return result

    # ---------------------------------------------------------- wire-format helper
    def handle_incoming(self, device_id: str, message: dict) -> Optional[CommandResult]:
        """Feed this to `websocket_server.on_message` (filtered to type=='remote_command')."""
        if message.get("type") != "remote_command":
            return None
        return self.execute(device_id, message.get("command", ""), message.get("args", {}))

    def _append_log(self, result: CommandResult) -> None:
        self._log.append(result.to_dict())
        self._log = self._log[-MAX_LOG_ENTRIES:]
        self._save_log()

    def history(self, limit: int = 50) -> List[dict]:
        return self._log[-limit:]

    def _load_log(self) -> None:
        if not os.path.exists(self.log_path):
            return
        try:
            with open(self.log_path, "r") as f:
                self._log = json.load(f).get("entries", [])
        except (json.JSONDecodeError, OSError):
            self._log = []

    def _save_log(self) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w") as f:
            json.dump({"entries": self._log}, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rc = RemoteController(log_path="ultron_data/cross_device/_demo_remote_log.json")
    rc.register_command("music.pause", lambda args: "paused")
    rc.grant("demo_phone", ["music.pause"])

    print(rc.execute("demo_phone", "music.pause"))
    print(rc.execute("demo_phone", "screen.lock"))  # unknown -> rejected
    print(rc.execute("unknown_device", "music.pause"))  # not granted -> rejected
