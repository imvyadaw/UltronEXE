"""Remote Access Control
=========================
Orchestrates system_control.network.remote_desktop.RemoteDesktop (RDP
toggle) and system_control.network.ssh_manager.SshManager (SSH host
service) - both already handle their own protocol on/off - by adding
the piece neither has: scoping access to one allowed IP via a
dedicated firewall rule, a single "grant temporary remote access"
call that turns both on and schedules automatic teardown, and a tie-in
to emergency_mode.EmergencyModeControl for an immediate full lockdown.
Outbound SSH (connecting FROM this machine) is
networking.ssh_client.py, a different module entirely - not touched
here.

Enabling access, widening the allowed IP, or extending the grant are
all confirm-gated - each one increases this machine's remote-access
exposure.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

_GRANT_PATH = Path(__file__).resolve().parent / "_remote_access_grant.json"
_FW_RULE_NAME = "ULTRON-ScopedRemoteAccess"


class RemoteAccessControl:
    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self) -> Dict:
        status = {}
        try:
            from system_control.network.remote_desktop import RemoteDesktop

            status["rdp"] = RemoteDesktop().get_status()
        except Exception as e:
            status["rdp"] = {"error": str(e)}
        try:
            from system_control.network.ssh_manager import SshManager

            status["ssh"] = SshManager().get_service_status()
        except Exception as e:
            status["ssh"] = {"error": str(e)}
        status["scoped_grant"] = self.get_grant_status()
        return status

    def _scope_firewall_to_ip(self, allowed_ip: str) -> Dict:
        script = (
            f"Remove-NetFirewallRule -DisplayName '{_FW_RULE_NAME}' -ErrorAction SilentlyContinue; "
            f"New-NetFirewallRule -DisplayName '{_FW_RULE_NAME}' -Direction Inbound -Action Allow "
            f"-Protocol TCP -LocalPort 3389,22 -RemoteAddress {allowed_ip} | Out-Null"
        )
        return self._run_ps(script)

    def _remove_firewall_scope(self) -> Dict:
        return self._run_ps(f"Remove-NetFirewallRule -DisplayName '{_FW_RULE_NAME}' -ErrorAction SilentlyContinue")

    def get_grant_status(self) -> Dict:
        if not _GRANT_PATH.exists():
            return {"active": False}
        try:
            grant = json.loads(_GRANT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"active": False}
        if grant.get("expires_at", 0) < time.time():
            return {"active": False, "expired_grant": grant}
        return {"active": True, **grant}

    def grant_temporary_access(
        self,
        allowed_ip: str,
        duration_minutes: int = 60,
        enable_rdp: bool = True,
        enable_ssh: bool = True,
        confirm: bool = False,
    ) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    f"This will enable {'RDP ' if enable_rdp else ''}{'SSH ' if enable_ssh else ''}"
                    f"scoped to only IP {allowed_ip} for {duration_minutes} minutes, then auto-revoke."
                ),
            }
        results = {}
        if enable_rdp:
            from system_control.network.remote_desktop import RemoteDesktop

            results["rdp"] = RemoteDesktop().set_enabled(True, confirm=True)
        if enable_ssh:
            from system_control.network.ssh_manager import SshManager

            ssh = SshManager()
            results["ssh_service"] = ssh.start_service(confirm=True)
        results["firewall_scope"] = self._scope_firewall_to_ip(allowed_ip)

        grant = {
            "allowed_ip": allowed_ip,
            "granted_at": time.time(),
            "expires_at": time.time() + duration_minutes * 60,
            "rdp": enable_rdp,
            "ssh": enable_ssh,
        }
        _GRANT_PATH.write_text(json.dumps(grant), encoding="utf-8")

        try:
            from automation.scheduler.task_scheduler import get_scheduler

            get_scheduler().run_after(duration_minutes * 60, self.revoke_all, task_id="remote_access_auto_revoke")
        except Exception as e:
            results["auto_revoke_scheduling"] = {"error": str(e)}
        return {"success": True, "grant": grant, "results": results}

    def extend_grant(self, additional_minutes: int, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will extend the current remote-access grant by {additional_minutes} minutes.",
            }
        status = self.get_grant_status()
        if not status.get("active"):
            return {"error": "No active grant to extend."}
        status["expires_at"] = status["expires_at"] + additional_minutes * 60
        _GRANT_PATH.write_text(json.dumps({k: v for k, v in status.items() if k != "active"}), encoding="utf-8")
        return {"success": True, "new_expiry": status["expires_at"]}

    def revoke_all(self, confirm: bool = True) -> Dict:
        """Turn off RDP + SSH and drop the scoped firewall rule. Called
        automatically by the scheduled auto-revoke, so it defaults to
        already-confirmed; pass confirm=False to preview when calling
        manually."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will disable RDP, stop the SSH service, and remove the scoped firewall rule.",
            }
        results = {}
        try:
            from system_control.network.remote_desktop import RemoteDesktop

            results["rdp"] = RemoteDesktop().set_enabled(False, confirm=True)
        except Exception as e:
            results["rdp"] = {"error": str(e)}
        try:
            from system_control.network.ssh_manager import SshManager

            results["ssh"] = SshManager().stop_service(confirm=True)
        except Exception as e:
            results["ssh"] = {"error": str(e)}
        results["firewall_scope"] = self._remove_firewall_scope()
        if _GRANT_PATH.exists():
            _GRANT_PATH.unlink()
        return {"success": True, "results": results}

    def emergency_lockdown(self, confirm: bool = False) -> Dict:
        """Thin pass-through to EmergencyModeControl.trigger() with only
        the remote-access piece engaged, for when the ask is specifically
        'cut off remote access now' rather than a full panic."""
        from system_control.special.emergency_mode import get_emergency_mode_control

        return get_emergency_mode_control().trigger(
            reason="remote_access_lockdown",
            lock_workstation=False,
            snapshot_webcam=False,
            lock_remote_access=True,
            confirm=confirm,
        )


_instance: Optional[RemoteAccessControl] = None


def get_remote_access_control() -> RemoteAccessControl:
    global _instance
    if _instance is None:
        _instance = RemoteAccessControl()
    return _instance
