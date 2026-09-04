r"""
Cross-device pairing tool wiring
========================
cross_device/device_manager.py, remote_controller.py, companion_api.py
and websocket_server.py were fully built and internally consistent,
but nothing in the AI tool loop could ever call `start_pairing()` -
there was no way for the user to actually get a 6-digit pairing code
out of Ultron to type into the Android companion app. This wasn't a
dormant-package gap (the servers do now start - see
cross_device/runtime.py); it was a missing *entry point* into an
otherwise-working feature.

Only pairing-initiation and a read-only device list are exposed here.
Granting commands to a device (`RemoteController.grant`) is
deliberately left as an explicit, by-hand call for the owner to make
in code - not something the assistant can do to itself via a tool
call, same reasoning as remote_controller.py's own "no generic
run-anything" design.
"""

import os
from typing import Dict


def _cross_device_enabled() -> bool:
    return os.getenv("ULTRON_CROSS_DEVICE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's _tool() - duplicated on
    purpose (see ai/new_skills_tools.py's docstring for why: avoids a
    circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _pair_new_device(args: Dict) -> Dict:
    try:
        from cross_device.device_manager import DeviceType
        from cross_device.runtime import get_cross_device

        device_type_raw = (args or {}).get("device_type", "phone")
        try:
            device_type = DeviceType(device_type_raw)
        except ValueError:
            device_type = DeviceType.OTHER

        state = get_cross_device()
        code = state["device_manager"].start_pairing(device_type)
        return {
            "success": True,
            "code": code,
            "expires_in_seconds": 300,
            "message": (
                f"Pairing code: {code}. Enter this along with this PC's LAN IP in the "
                "ULTRON Companion app within 5 minutes."
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _list_paired_devices(args: Dict) -> Dict:
    try:
        from cross_device.runtime import get_cross_device

        state = get_cross_device()
        devices = state["device_manager"].list_devices()
        return {
            "success": True,
            "devices": [
                {
                    "device_id": d.device_id,
                    "name": d.name,
                    "device_type": d.device_type.value,
                    "last_seen": d.last_seen,
                }
                for d in devices
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


CROSS_DEVICE_DIRECT_HANDLERS = {
    "pair_new_device": _pair_new_device,
    "list_paired_devices": _list_paired_devices,
}

# Schema visibility itself is gated - the model never sees a tool it
# can't use, it doesn't just get refused after trying (same convention
# as ai/phase30_gated_tools.py's PHASE30_GATED_TOOLS).
CROSS_DEVICE_TOOLS = []

if _cross_device_enabled():
    CROSS_DEVICE_TOOLS.append(
        _tool(
            "pair_new_device",
            "Start pairing a new companion device (e.g. the ULTRON Android app). Generates a "
            "6-digit code, valid for 5 minutes, that the user enters in the companion app "
            "along with this PC's LAN IP to complete pairing.",
            {
                "device_type": {
                    "type": "string",
                    "enum": ["phone", "tablet", "desktop", "laptop", "watch", "other"],
                    "description": "Type of device being paired. Defaults to 'phone'.",
                }
            },
        )
    )
    CROSS_DEVICE_TOOLS.append(
        _tool(
            "list_paired_devices",
            "List devices currently paired with ULTRON's companion app (name, type, last "
            "seen). Does not include tokens.",
        )
    )
