"""Startup Manager
==================
Manage what launches at logon: list every startup entry (registry Run
keys + the Startup folder, same set Task Manager's Startup tab and
msconfig show), add/remove a Run-key entry, and enable/disable an
entry the same way Task Manager does (via the StartupApproved binary
flag) without deleting it.

Reading uses Get-CimInstance Win32_StartupCommand (covers Run keys,
RunOnce, and the Startup folder in one call, same approach
system_properties.py/device_manager.py use for other WMI-backed info).
Writes go through `winreg` directly (HKCU only, same restriction
registry_manager.py already draws - HKLM Run entries affect every
user and need admin, so they're add/remove-blocked here the same way
registry_manager.py blocks HKLM writes outright).
"""

import json
import subprocess
from typing import Dict

try:
    import winreg

    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_APPROVED_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
# Task Manager's own on/off encoding for StartupApproved\Run values.
_ENABLED_VALUE = bytes([0x02] + [0x00] * 11)
_DISABLED_VALUE = bytes([0x03] + [0x00] * 11)


class StartupManager:
    """List/add/remove/enable/disable programs that launch at logon."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_startup_items(self) -> Dict:
        """List every startup entry: Run/RunOnce registry keys plus the
        Startup folder, for both the current user and all users."""
        cmd = "Get-CimInstance Win32_StartupCommand | Select-Object Name,Command,Location,User " "| ConvertTo-Json"
        result = self._run_ps(cmd)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-CimInstance Win32_StartupCommand failed"}
        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            items = data if isinstance(data, list) else [data]
        except Exception as e:
            return {"error": f"Could not parse output: {e}", "raw": result["stdout"]}
        return {"success": True, "startup_items": items, "count": len(items)}

    def add_startup_item(self, name: str, command: str, confirm: bool = False) -> Dict:
        """Add a program to the current user's startup (HKCU Run key).
        Confirm-gated. System-wide (HKLM/all-users) startup entries are
        not supported here - same HKCU-only boundary registry_manager.py
        draws for every other write."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if not name or not command:
            return {"error": "name and command must both be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would add startup entry {name!r} -> {command!r} (current user only)",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
            return {"success": True, "name": name, "command": command}
        except PermissionError:
            return {"error": "Access denied writing to the Run key."}
        except Exception as e:
            return {"error": str(e)}

    def remove_startup_item(self, name: str, confirm: bool = False) -> Dict:
        """Remove a program from the current user's startup (HKCU Run
        key). Confirm-gated."""
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if not name:
            return {"error": "name must be non-empty"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove startup entry {name!r} (current user only)",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            return {"success": True, "name": name, "removed": True}
        except FileNotFoundError:
            return {"error": f"No startup entry named {name!r} found in HKCU Run"}
        except PermissionError:
            return {"error": "Access denied writing to the Run key."}
        except Exception as e:
            return {"error": str(e)}

    def enable_startup_item(self, name: str, confirm: bool = False) -> Dict:
        """Re-enable a Task-Manager-disabled startup entry without
        deleting it (writes the same 'enabled' flag Task Manager's
        Startup tab does). Confirm-gated."""
        return self._toggle_approved(name, enable=True, confirm=confirm)

    def disable_startup_item(self, name: str, confirm: bool = False) -> Dict:
        """Disable a startup entry without removing it (the Task-Manager
        way - flips the StartupApproved flag rather than deleting the
        Run-key entry, so it can be re-enabled later). Confirm-gated."""
        return self._toggle_approved(name, enable=False, confirm=confirm)

    def _toggle_approved(self, name: str, enable: bool, confirm: bool) -> Dict:
        if not HAS_WINREG:
            return {"error": "winreg is only available on Windows"}
        if not name:
            return {"error": "name must be non-empty"}
        action = "enable" if enable else "disable"
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {action} startup entry {name!r} (current user only)",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, _STARTUP_APPROVED_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                value = _ENABLED_VALUE if enable else _DISABLED_VALUE
                winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, value)
            return {"success": True, "name": name, "action": action}
        except PermissionError:
            return {"error": "Access denied writing to the StartupApproved key."}
        except Exception as e:
            return {"error": str(e)}
