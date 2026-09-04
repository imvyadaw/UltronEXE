"""
runtime.py
====================
Wires device_manager.py, remote_controller.py, companion_api.py and
websocket_server.py into one running set of servers, and makes them
reachable as a single lazy singleton - the same pattern used by
ai/tool_runtime.py's `_get_web_tools()` and ai/new_skills_tools.py's
`_get()`.

Why this file exists: `DeviceManager` keeps in-flight pairing codes
in memory (not on disk), so core/assistant.py and any AI tool handler
that wants to trigger/inspect pairing MUST share the exact same
`DeviceManager`/`RemoteController` instances the running
`CompanionWebSocketServer` authenticates against - two separately
constructed `DeviceManager()` objects would silently never see each
other's pending codes. `get_cross_device()` guarantees there is ever
only one of each, built and started once per process.

Call `get_cross_device()` to obtain (and start, on first call) the
dict `{"device_manager", "remote_controller", "api", "ws_server"}`.
Safe to call repeatedly/from multiple threads - only the first caller
actually starts anything.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("ultron.cross_device.runtime")

_lock = threading.Lock()
_state: Optional[Dict[str, Any]] = None


def _env_host() -> str:
    # Default to LAN-reachable so a paired phone can actually connect;
    # override with ULTRON_CROSS_DEVICE_HOST=127.0.0.1 to restrict to
    # this machine only.
    return os.environ.get("ULTRON_CROSS_DEVICE_HOST", "0.0.0.0")


def _env_port(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _run_ws_server_forever(ws_server) -> None:
    """CompanionWebSocketServer is asyncio-based; give it its own event
    loop on a dedicated daemon thread so it doesn't require the rest of
    the (largely synchronous) assistant to be async."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ws_server.start())
        loop.run_forever()
    except Exception:
        logger.exception("[cross_device] websocket server loop crashed")
    finally:
        loop.close()


def get_cross_device() -> Dict[str, Any]:
    """Build (once) and return the shared cross_device runtime state,
    starting CompanionAPI and CompanionWebSocketServer in background
    threads on first call."""
    global _state
    if _state is not None:
        return _state

    with _lock:
        if _state is not None:
            return _state

        from cross_device.device_manager import DeviceManager
        from cross_device.remote_controller import RemoteController
        from cross_device.companion_api import CompanionAPI
        from cross_device.websocket_server import CompanionWebSocketServer

        device_manager = DeviceManager()
        remote_controller = RemoteController()

        api = CompanionAPI(
            device_manager,
            remote_controller,
            host=_env_host(),
            port=_env_port("ULTRON_CROSS_DEVICE_HTTP_PORT", 8766),
        )
        ws_server = CompanionWebSocketServer(
            device_manager,
            host=_env_host(),
            port=_env_port("ULTRON_CROSS_DEVICE_WS_PORT", 8765),
        )

        async def _on_message(device_id: str, message: dict):
            # RemoteController.handle_incoming is sync; websocket_server's
            # on_message contract is async, so just call it inline - it
            # does no I/O of its own beyond the in-memory log write.
            return remote_controller.handle_incoming(device_id, message)

        ws_server.on_message(_on_message)

        api.start_in_thread()
        threading.Thread(
            target=_run_ws_server_forever, args=(ws_server,), daemon=True, name="cross-device-ws"
        ).start()

        logger.info(
            "[cross_device] CompanionAPI on %s:%s, CompanionWebSocketServer on %s:%s",
            api.host, api.port, ws_server.host, ws_server.port,
        )

        _state = {
            "device_manager": device_manager,
            "remote_controller": remote_controller,
            "api": api,
            "ws_server": ws_server,
        }
        return _state
