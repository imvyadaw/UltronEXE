"""
Admin-elevation tool wiring
=============================
windows/system_info/admin.py's is_admin()/get_admin_status()/
relaunch_as_admin() are new (see that file's docstring for why: no
elevation check existed anywhere in the project before, which is
almost certainly the real cause behind "bahut kuch fail ho jata hai,
direct permission nahi hai" - firewall/service/kill_process/etc.
failing with a bare OS error and no explanation). Wired here the same
lazy-handler-dict way as ai/self_management_tools.py.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
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


ADMIN_TOOLS = [
    _tool(
        "get_admin_status",
        "Check whether Ultron is currently running with Windows Administrator rights. Call "
        "this BEFORE attempting (or when explaining a failure from) firewall rule changes, "
        "service start/stop/enable, kill_process on a process the user doesn't own, "
        "machine-wide startup-program removal, or Defender policy changes - all of these "
        "need admin rights and fail with a plain access-denied error otherwise.",
    ),
    _tool(
        "relaunch_as_admin",
        "Close the current Ultron session and reopen it as Administrator (triggers a Windows "
        "UAC consent prompt the user must approve). Only call with confirm:true after the "
        "user has clearly agreed - this ends the current session.",
        {"confirm": {"type": "boolean", "description": "Must be true to actually relaunch."}},
    ),
]

ADMIN_DIRECT_HANDLERS: Dict = {
    "get_admin_status": lambda a: __import__(
        "windows.system_info.admin", fromlist=["get_admin_status"]
    ).get_admin_status(),
    "relaunch_as_admin": lambda a: __import__(
        "windows.system_info.admin", fromlist=["relaunch_as_admin"]
    ).relaunch_as_admin(confirm=bool(a.get("confirm", False))),
}
