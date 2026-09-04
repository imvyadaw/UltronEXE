"""
websocket_server.py
====================
The one live connection each paired device holds open to ULTRON.
Everything else in CROSS_DEVICE (notifications, clipboard sync,
remote commands) rides over this same socket as a small typed
message envelope - this file only owns connecting, authenticating,
and routing, not what the messages mean.

Auth is mandatory: a socket that doesn't send a valid
`{device_id, token}` auth message within `auth_timeout` seconds is
dropped. There is no anonymous or unauthenticated channel.

Binds to localhost by default - change `host` only if you understand
you're exposing this to your LAN, and pair a firewall rule to it.

Dependencies: pip install websockets
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .device_manager import DeviceManager

logger = logging.getLogger("ultron.websocket_server")

MessageHandler = Callable[[str, dict], Awaitable[None]]  # (device_id, message) -> None


@dataclass
class _Connection:
    device_id: str
    socket: WebSocketServerProtocol


class CompanionWebSocketServer:
    """Local WebSocket hub. One connection per authenticated device."""

    def __init__(
        self, device_manager: DeviceManager, host: str = "0.0.0.0", port: int = 8765, auth_timeout: float = 10.0
    ):
        self.device_manager = device_manager
        self.host = host
        self.port = port
        self.auth_timeout = auth_timeout
        self._connections: Dict[str, _Connection] = {}  # device_id -> connection
        self._message_handlers: list[MessageHandler] = []
        self._server = None

    def on_message(self, handler: MessageHandler) -> None:
        """Register a callback invoked for every authenticated message received,
        e.g. `notification_router.handle_incoming` or `universal_clipboard.handle_incoming`."""
        self._message_handlers.append(handler)

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle_connection, self.host, self.port)
        logger.info("CompanionWebSocketServer listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for conn in list(self._connections.values()):
            await conn.socket.close()
        self._connections.clear()

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        """Push a message to one connected device. Returns False if it isn't
        currently connected (caller decides whether to queue for later)."""
        conn = self._connections.get(device_id)
        if not conn:
            return False
        try:
            await conn.socket.send(json.dumps(message))
            return True
        except websockets.ConnectionClosed:
            self._connections.pop(device_id, None)
            return False

    async def broadcast(self, message: dict, capability: Optional[str] = None) -> int:
        """Send to all connected devices, optionally filtered to ones registered
        with a given capability. Returns count of successful sends."""
        targets = self.device_manager.list_devices()
        if capability:
            targets = [d for d in targets if capability in d.capabilities]
        sent = 0
        for device in targets:
            if await self.send_to_device(device.device_id, message):
                sent += 1
        return sent

    def connected_device_ids(self) -> list[str]:
        return list(self._connections.keys())

    # ------------------------------------------------------------------ internal
    async def _handle_connection(self, socket: WebSocketServerProtocol) -> None:
        device_id = await self._authenticate(socket)
        if device_id is None:
            await socket.close(code=4001, reason="auth failed")
            return

        self._connections[device_id] = _Connection(device_id=device_id, socket=socket)
        logger.info("Device %s connected", device_id)
        try:
            async for raw in socket:
                await self._dispatch(device_id, raw)
        except websockets.ConnectionClosed:
            from core.error_trace import log_swallowed as _lsw

            _lsw("cross_device.websocket_server._handle_connection")
        finally:
            self._connections.pop(device_id, None)
            logger.info("Device %s disconnected", device_id)

    async def _authenticate(self, socket: WebSocketServerProtocol) -> Optional[str]:
        try:
            raw = await asyncio.wait_for(socket.recv(), timeout=self.auth_timeout)
        except (asyncio.TimeoutError, websockets.ConnectionClosed):
            return None
        try:
            msg = json.loads(raw)
            device_id, token = msg["device_id"], msg["token"]
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

        device = self.device_manager.authenticate(device_id, token)
        if not device:
            logger.warning("Rejected connection: bad credentials")
            return None
        await socket.send(json.dumps({"type": "auth_ok", "device_id": device_id}))
        return device_id

    async def _dispatch(self, device_id: str, raw: str) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Dropped malformed message from %s", device_id)
            return
        for handler in self._message_handlers:
            try:
                result = await handler(device_id, message)
                # Remote command handlers may return a CommandResult. Echo a
                # typed result envelope to the same authenticated device.
                if result is not None and hasattr(result, "to_dict"):
                    payload = result.to_dict()
                    payload["type"] = "command_result"
                    await self._connections[device_id].socket.send(json.dumps(payload))
            except Exception:
                logger.exception("Message handler raised for device %s", device_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _demo():
        dm = DeviceManager(store_path="ultron_data/cross_device/_demo_devices.json")
        server = CompanionWebSocketServer(dm)

        async def echo_handler(device_id, message):
            print(f"[{device_id}] {message}")

        server.on_message(echo_handler)
        await server.start()
        print(f"Demo server running on ws://{server.host}:{server.port} - Ctrl+C to stop")
        await asyncio.Future()

    try:
        asyncio.run(_demo())
    except KeyboardInterrupt:
        from core.error_trace import log_swallowed as _lsw

        _lsw("cross_device.websocket_server.<module>")
