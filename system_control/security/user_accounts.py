"""User Accounts Manager
=========================
Local Windows user account control via `net user`/PowerShell
LocalAccounts cmdlets - list accounts, get status, create/remove,
enable/disable, change group membership (admin vs standard), and
reset a local password. Distinct from apps/system/control_panel.py's
"user_accounts" entry (just opens the nusrmgr.cpl GUI applet) and
from top-level security/authentication.py + voice_lock.py/face_lock.py
(ULTRON's OWN unlock/authentication layer, not Windows OS accounts) -
this is real programmatic control over Windows local user accounts.

Listing accounts and status are plain reads. Every account-modifying
method (create, remove, enable/disable, group changes, password
resets) is confirm-gated and needs admin - these directly control who
can log into this machine and with what privileges.
"""

import subprocess
from typing import Dict


class UserAccountsManager:
    """Inspect and control local Windows user accounts via net user / PowerShell."""

    def _run(self, cmd: list, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": f"{cmd[0]} not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        return self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)

    def _admin_hint(self, err: str) -> str:
        if err and (
            "denied" in err.lower()
            or "not authorized" in err.lower()
            or "elevat" in err.lower()
            or "access is denied" in err.lower()
        ):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def list_accounts(self) -> Dict:
        """List local Windows user accounts with enabled/admin status."""
        result = self._run_ps("Get-LocalUser | Select-Object Name, Enabled, Description, LastLogon | ConvertTo-Json")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-LocalUser failed")}
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
        except Exception:
            return {"error": "Could not parse account list.", "raw": result["stdout"]}
        admins_result = self._run_ps("(Get-LocalGroupMember -Group 'Administrators').Name")
        admin_names = set()
        if admins_result.get("success"):
            admin_names = {n.split("\\")[-1] for n in admins_result["stdout"].splitlines() if n.strip()}
        accounts = [
            {
                "name": a.get("Name"),
                "enabled": a.get("Enabled"),
                "description": a.get("Description"),
                "last_logon": a.get("LastLogon"),
                "is_admin": a.get("Name") in admin_names,
            }
            for a in data
        ]
        return {"accounts": accounts, "count": len(accounts)}

    def get_account_status(self, username: str) -> Dict:
        """Get status for a single local account by username."""
        listed = self.list_accounts()
        if "error" in listed:
            return listed
        for a in listed["accounts"]:
            if a["name"] and a["name"].lower() == username.lower():
                return a
        return {"error": f"No local account named '{username}' found."}

    def create_account(self, username: str, password: str, make_admin: bool = False, confirm: bool = False) -> Dict:
        """Create a new local user account. Confirm-gated and needs admin -
        this directly grants a new login to this machine."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will create a new local account '{username}'"
                + (" with Administrator privileges." if make_admin else " as a standard user."),
            }
        result = self._run(["net", "user", username, password, "/add"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net user /add failed")}
        if make_admin:
            grp = self._run(["net", "localgroup", "Administrators", username, "/add"])
            if not grp.get("success"):
                return {
                    "success": True,
                    "created": username,
                    "admin_grant_failed": self._admin_hint(grp.get("stderr") or "group add failed"),
                }
        return {"success": True, "created": username, "is_admin": make_admin}

    def remove_account(self, username: str, confirm: bool = False) -> Dict:
        """Delete a local user account. Confirm-gated and needs admin -
        irreversible without a backup of that profile."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will DELETE the local account '{username}' - this cannot be undone.",
            }
        result = self._run(["net", "user", username, "/delete"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net user /delete failed")}
        return {"success": True, "removed": username}

    def set_account_enabled(self, username: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable a local account (disabling blocks login without
        deleting the account/profile). Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'ENABLE' if enabled else 'DISABLE'} login for '{username}'.",
            }
        result = self._run(["net", "user", username, "/active:" + ("yes" if enabled else "no")])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net user /active failed")}
        return {"success": True, "username": username, "enabled": enabled}

    def set_admin(self, username: str, is_admin: bool, confirm: bool = False) -> Dict:
        """Add or remove a user from the local Administrators group. Confirm-gated,
        needs admin - this directly changes what that account can do on this
        machine."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'GRANT' if is_admin else 'REVOKE'} Administrator privileges for '{username}'.",
            }
        args = ["net", "localgroup", "Administrators", username, "/add" if is_admin else "/delete"]
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net localgroup failed")}
        return {"success": True, "username": username, "is_admin": is_admin}

    def reset_password(self, username: str, new_password: str, confirm: bool = False) -> Dict:
        """Reset a local account's password. Confirm-gated - the new password
        is passed as a one-off command-line argument, and this invalidates
        the account's current credential/access (e.g. any saved DPAPI
        secrets tied to the old password)."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will RESET the password for '{username}' - saved credentials/encrypted "
                f"data tied to their old password (e.g. saved Wi-Fi keys, browser-saved logins) "
                f"may become inaccessible to them.",
            }
        result = self._run(["net", "user", username, new_password])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "net user password reset failed")}
        return {"success": True, "username": username}
