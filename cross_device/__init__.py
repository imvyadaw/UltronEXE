"""
CROSS_DEVICE
============
Lets ULTRON follow you across your own devices: a phone, a tablet, a
second PC. Everything here talks over your local network (or a
network you explicitly configure) using a token you generate - there
is no cloud relay, no third-party pairing service, and no device is
ever contacted unless you registered it yourself first.

Each submodule is imported independently and set to None if its
dependency isn't installed (e.g. `websockets` for
CompanionWebSocketServer/CompanionAPI) - matching this project's
existing best-effort convention - so DeviceManager and the other
dependency-free pieces still work without it.
"""

import logging

logger = logging.getLogger("ultron.cross_device")


def _optional_import(module_name: str, *names):
    try:
        module = __import__(f"cross_device.{module_name}", fromlist=list(names))
        return tuple(getattr(module, n) for n in names)
    except ImportError as e:
        logger.info("[cross_device] %s unavailable (%s) - continuing without it", module_name, e)
        return tuple(None for _ in names)


DeviceManager, Device, DeviceType = _optional_import("device_manager", "DeviceManager", "Device", "DeviceType")
(CompanionWebSocketServer,) = _optional_import("websocket_server", "CompanionWebSocketServer")
NotificationRouter, Notification, Priority = _optional_import(
    "notification_router", "NotificationRouter", "Notification", "Priority"
)
UniversalClipboard, ClipboardEntry = _optional_import("universal_clipboard", "UniversalClipboard", "ClipboardEntry")
(RemoteController,) = _optional_import("remote_controller", "RemoteController")
(CompanionAPI,) = _optional_import("companion_api", "CompanionAPI")

__all__ = [
    "DeviceManager",
    "Device",
    "DeviceType",
    "CompanionWebSocketServer",
    "NotificationRouter",
    "Notification",
    "Priority",
    "UniversalClipboard",
    "ClipboardEntry",
    "RemoteController",
    "CompanionAPI",
]
