"""Environment Variables
========================
Read/set/delete user and system environment variables.

Reads always come straight from `os.environ` (the running process's
view - fast, no subprocess). Writes/deletes go through `setx`
(user-scope by default, `/M` for system-scope) since that's the
supported way to persist an env var change for *future* processes on
Windows - directly editing the registry's Environment key would work
too but setx already broadcasts the WM_SETTINGCHANGE message so other
apps notice the change, which a raw registry write does not.

Safety model:
  - User-scope (default) set/delete: confirm-gated, no other restriction.
  - System-scope (scope="system"): confirm-gated AND needs admin - setx
    itself will fail with a clear permission error if not elevated, and
    we surface that rather than trying to auto-elevate.
  - A change made via setx does NOT affect the *current* ULTRON process's
    os.environ (only new processes see it) - callers are told this in
    the response so they don't expect get_variable to reflect it
    immediately without a restart.
"""
import logging

import os
import subprocess
from typing import Dict


class EnvironmentVariables:
    """Get/set/delete/list environment variables (user or system scope)."""

    def get_variable(self, name: str) -> Dict:
        """Read a variable from the current process's environment."""
        if not name:
            return {"error": "name must be non-empty"}
        value = os.environ.get(name)
        if value is None:
            return {"success": False, "error": f"'{name}' is not set in the current environment"}
        return {"success": True, "name": name, "value": value}

    def list_variables(self, filter_prefix: str = "") -> Dict:
        """List all variables in the current process's environment,
        optionally filtered by name prefix (case-insensitive)."""
        prefix_l = (filter_prefix or "").lower()
        items = {k: v for k, v in os.environ.items() if k.lower().startswith(prefix_l)}
        return {"success": True, "variables": items, "count": len(items)}

    def set_variable(self, name: str, value: str, scope: str = "user", confirm: bool = False) -> Dict:
        """Persist a variable via `setx` (user or system scope). Only
        affects future processes - not this running one."""
        if not name:
            return {"error": "name must be non-empty"}
        scope = (scope or "user").lower()
        if scope not in ("user", "system"):
            return {"error": "scope must be 'user' or 'system'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set {scope}-scope environment variable {name}={value!r} via setx"
                f"{' (/M, needs admin)' if scope == 'system' else ''}",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            cmd = ["setx", name, value]
            if scope == "system":
                cmd.append("/M")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip() or "setx failed"
                if scope == "system" and ("access" in err.lower() or "denied" in err.lower()):
                    err += " - system-scope variables need ULTRON to be running as Administrator."
                return {"error": err}
            return {
                "success": True,
                "name": name,
                "value": value,
                "scope": scope,
                "note": "Takes effect for new processes only - not the currently running ULTRON process.",
            }
        except FileNotFoundError:
            return {"error": "setx not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "setx timed out"}
        except Exception as e:
            return {"error": str(e)}

    def delete_variable(self, name: str, scope: str = "user", confirm: bool = False) -> Dict:
        """Delete a persisted variable. setx has no native delete, so this
        clears the value via the registry Environment key directly
        (HKCU\\Environment for user scope, HKLM\\SYSTEM\\...\\Environment
        for system scope) and broadcasts the same change notification
        setx does, so running apps still notice."""
        if not name:
            return {"error": "name must be non-empty"}
        scope = (scope or "user").lower()
        if scope not in ("user", "system"):
            return {"error": "scope must be 'user' or 'system'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete {scope}-scope environment variable '{name}'",
                "message": "Call again with confirm=true to apply.",
            }
        try:
            import winreg
        except ImportError:
            return {"error": "winreg is only available on Windows"}
        try:
            if scope == "user":
                root, key_path, access = winreg.HKEY_CURRENT_USER, "Environment", winreg.KEY_SET_VALUE
            else:
                root = winreg.HKEY_LOCAL_MACHINE
                key_path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
                access = winreg.KEY_SET_VALUE
            with winreg.OpenKey(root, key_path, 0, access) as key:
                winreg.DeleteValue(key, name)
            self._broadcast_env_change()
            return {
                "success": True,
                "deleted": name,
                "scope": scope,
                "note": "Takes effect for new processes only - not the currently running ULTRON process.",
            }
        except FileNotFoundError:
            return {"error": f"'{name}' is not set at {scope} scope"}
        except PermissionError:
            return {"error": f"Permission denied - {scope}-scope deletes need ULTRON running as Administrator."}
        except Exception as e:
            return {"error": str(e)}

    def _broadcast_env_change(self) -> None:
        """Best-effort WM_SETTINGCHANGE broadcast so other running apps
        notice the deletion, same as setx does for sets. Purely cosmetic -
        failure here doesn't affect whether the delete itself succeeded."""
        try:
            import ctypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            ctypes.windll.user32.SendMessageTimeoutW(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,
                None,
            )
        except Exception:
            logging.getLogger(__name__).exception("Suppressed Exception")
