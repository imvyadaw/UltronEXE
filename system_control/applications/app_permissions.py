"""App Execution Permissions
============================
Whether a program is *allowed to run at all* on this account, via the
per-user Software Restriction Policy `DisallowRun` list (
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer)
- the same mechanism Group Policy's "Don't run specified Windows
applications" uses. This is deliberately a different axis from every
other permission-shaped module already in the codebase:

- system_control/security/app_permissions.py - whether an *already-
  running/installed* app may use a sensor/data category (camera, mic,
  location, ...). Not covered here.
- system_control/network/firewall_manager.py's block_program/
  allow_program - whether an app may reach the *network*, not whether
  it may launch at all. Not covered here.
- system_control/applications/app_settings.py's
  set_run_as_administrator - how an app runs (elevated or not), not
  whether it's permitted to run. Not covered here.

This module is specifically "can Explorer/the shell launch this exe by
name at all" - a coarse, per-user, easily-reversible execution
allowlist/blocklist, useful for e.g. temporarily locking a distracting
or risky app out of launching.

Enforcement is Explorer-level (DisallowRun only stops launches that go
through the shell - Explorer double-click, Start menu, Run dialog);
it is not a security boundary against a determined user with direct
process-creation access, and is documented as a *convenience* lock,
not a sandbox.
"""

import winreg
from typing import Dict, List


class AppExecutionPolicy:
    """Per-user allow/block list for which exe names Explorer will
    launch, via the DisallowRun Software Restriction Policy."""

    _POLICY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    _DISALLOW_PATH = _POLICY_PATH + r"\DisallowRun"

    def is_execution_restriction_enabled(self) -> Dict:
        """Read whether the DisallowRun policy is currently enforced at
        all (the master switch - individual blocked names in
        DisallowRun\\* are ignored unless this is set). No admin
        needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._POLICY_PATH) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "DisallowRun")
                    return {"enabled": bool(value)}
                except FileNotFoundError:
                    return {"enabled": False}
        except FileNotFoundError:
            return {"enabled": False}

    def set_execution_restriction_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Toggle the DisallowRun master switch. Confirm-gated - with
        this off, every name in list_blocked_apps() is silently
        ignored and every app can launch again."""
        if not confirm:
            action = "enable" if enabled else "disable"
            return {
                "requires_confirmation": True,
                "preview": f"This will {action} app-execution restriction enforcement for this user.",
            }
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._POLICY_PATH) as key:
                winreg.SetValueEx(key, "DisallowRun", 0, winreg.REG_DWORD, 1 if enabled else 0)
            return {"success": True, "enabled": enabled}
        except OSError as e:
            return {"error": str(e)}

    def list_blocked_apps(self) -> Dict:
        """List every exe name currently in the DisallowRun blocklist.
        No admin needed."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._DISALLOW_PATH) as key:
                names: List[str] = []
                i = 0
                while True:
                    try:
                        _, value, _ = winreg.EnumValue(key, i)
                        names.append(value)
                        i += 1
                    except OSError:
                        break
                return {"blocked": sorted(names), "count": len(names)}
        except FileNotFoundError:
            return {"blocked": [], "count": 0}

    def block_app_execution(self, exe_name: str, confirm: bool = False) -> Dict:
        """Add an exe name (e.g. 'steam.exe') to the DisallowRun list
        so Explorer refuses to launch it. Also ensures the master
        switch is on, since a blocked name with enforcement off has no
        effect. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will block '{exe_name}' from being launched via Explorer/Start/Run for this user.",
            }
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._POLICY_PATH) as pkey:
                winreg.SetValueEx(pkey, "DisallowRun", 0, winreg.REG_DWORD, 1)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._DISALLOW_PATH) as key:
                existing = self.list_blocked_apps().get("blocked", [])
                if exe_name in existing:
                    return {"success": True, "exe_name": exe_name, "already_blocked": True}
                # Value names under DisallowRun are just sequential numbers ("1", "2", ...)
                next_index = str(len(existing) + 1)
                winreg.SetValueEx(key, next_index, 0, winreg.REG_SZ, exe_name)
            return {"success": True, "exe_name": exe_name, "blocked": True}
        except OSError as e:
            return {"error": str(e)}

    def allow_app_execution(self, exe_name: str, confirm: bool = False) -> Dict:
        """Remove an exe name from the DisallowRun list, restoring its
        ability to launch. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will remove the block on '{exe_name}', allowing it to launch again.",
            }
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._DISALLOW_PATH, 0, winreg.KEY_ALL_ACCESS) as key:
                i = 0
                target_name = None
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        if value == exe_name:
                            target_name = name
                            break
                        i += 1
                    except OSError:
                        break
                if target_name is None:
                    return {"success": True, "exe_name": exe_name, "was_blocked": False}
                winreg.DeleteValue(key, target_name)
            return {"success": True, "exe_name": exe_name, "allowed": True}
        except FileNotFoundError:
            return {"success": True, "exe_name": exe_name, "was_blocked": False}
        except OSError as e:
            return {"error": str(e)}
