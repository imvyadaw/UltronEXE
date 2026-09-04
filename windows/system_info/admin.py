"""
Admin / elevation status
=========================
Checks whether Ultron's own process is running with Windows
Administrator rights, and can relaunch it elevated if not.

Why this exists: confirmed by searching the whole codebase - nothing
anywhere ever called IsUserAnAdmin() or any equivalent check. Firewall
rule changes (windows/firewall/rules.py), service start/stop/enable
(windows/services/controller.py), killing a process you don't own,
startup-program removal from HKLM, and some Defender settings all
genuinely require admin rights on Windows - and when Ultron isn't
running elevated, every one of those just returns whatever raw error
Windows gives (a non-zero exit code from netsh/sc, or "Access is
denied"), with nothing telling the user *why* or that the fix is as
simple as restarting Ultron as Administrator. That's almost certainly
what "bahut kuch fail ho jata hai, direct permission nahi hai" (lots
of things fail, it doesn't have direct permission) was pointing at.

is_admin() uses the standard Win32 IsUserAnAdmin() check (read-only,
no side effects, instant - safe to call on every boot).
relaunch_as_admin() uses ShellExecuteW's "runas" verb, which is the
exact same OS action as right-clicking an app and choosing "Run as
administrator" - Windows shows its own UAC consent dialog and the
person at the keyboard has to click Yes; nothing here can silently
grant elevation on its own.
"""

import os
import sys
import ctypes
from typing import Dict

# Not exhaustive - just the admin-gated actions this project already
# implements, used to explain get_admin_status()'s "affects" list.
ADMIN_REQUIRED_ACTIONS = {
    "firewall rules": "add_allow_rule / add_block_rule / delete rule",
    "service control": "start_service / stop_service / enabling a service",
    "kill_process (system or other users' processes)": "kill_process on anything you don't own",
    "startup program removal (machine-wide)": "remove_startup_program when it's in HKLM, not HKCU",
    "some Defender settings": "Set-MpPreference-style machine-wide policy changes",
}


def is_admin() -> bool:
    """True if this process currently has Administrator rights. Windows
    only - returns False (not an error) on any other platform, or if
    the check itself fails for any reason, since "assume not elevated"
    is the safe default either way."""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_admin_status() -> Dict:
    """Report elevation status plus a plain-language explanation - used
    both as an AI tool (get_admin_status) and by core/startup.py's boot
    report, so this is visible every run instead of only when the user
    thinks to ask after something already failed."""
    elevated = is_admin()
    if elevated:
        return {
            "elevated": True,
            "message": "Running as Administrator - firewall, service control, and "
            "other admin-only actions will work normally.",
        }
    return {
        "elevated": False,
        "message": (
            "Not running as Administrator. Firewall rule changes, service "
            "start/stop/enable, killing processes you don't own, machine-wide "
            "startup-program removal, and some Defender settings will fail with "
            "an access-denied error until Ultron is restarted elevated - say "
            "'restart as admin', or right-click the shortcut and choose "
            "'Run as administrator'."
        ),
        "affects": sorted(ADMIN_REQUIRED_ACTIONS.keys()),
    }


def permission_denied_hint(action: str) -> str:
    """One-line suffix for any admin-gated tool's own error message when
    it fails and Ultron isn't elevated, so the failure is actionable
    instead of a bare OS error code. Callers only need to check
    `if not is_admin(): msg += permission_denied_hint(...)` around their
    existing error path - this never changes what the error dict looks
    like structurally, just adds context."""
    return (
        f" ({action} needs Administrator rights - Ultron isn't running elevated. "
        f"Say 'restart as admin' or relaunch it as Administrator.)"
    )


def relaunch_as_admin(confirm: bool = False) -> Dict:
    """Relaunch the current Ultron process elevated, then exit this one.
    Triggers Windows' own UAC consent prompt - the person at the
    keyboard has to approve it, exactly like manually choosing "Run as
    administrator"; this cannot grant elevation silently. Safety-gated
    like every other tool that ends the current process (see
    windows/system_info/power.py's shutdown_pc/restart_pc) - also
    listed in core/permissions.py's DESTRUCTIVE_TOOLS."""
    if sys.platform != "win32":
        return {"error": "Administrator elevation is a Windows-only concept."}
    if is_admin():
        return {"success": True, "message": "Already running as Administrator - nothing to do."}
    if not confirm:
        return {
            "error": "This closes the current Ultron session and reopens it elevated "
            "(you'll see a Windows UAC prompt to approve). Call again with "
            "confirm=true to proceed."
        }
    try:
        params = " ".join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        # ShellExecuteW returns > 32 on success; <= 32 is a Win32 error
        # code (e.g. 5 = the user clicked "No" on the UAC prompt).
        if ret > 32:
            os._exit(0)  # the elevated copy is starting on its own; let this one go
        return {"error": f"Elevation request failed or was declined (code {ret})."}
    except Exception as e:
        return {"error": str(e)}
