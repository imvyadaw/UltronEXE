"""SSH Manager (server/host side)
===================================
Controls the OpenSSH SERVER (sshd) optional Windows feature and
service on THIS machine - install/uninstall the capability, start/
stop/enable the sshd service, check listening status, and manage
authorized_keys for a user. This is the inbound/host side.

Distinct from networking/ssh_client.py, which is the *outbound*
SSH protocol client this machine uses to connect elsewhere - that
module opens connections; this one controls whether other machines
can open a connection into this one.

Reads (get_status, list_authorized_keys) work without admin.
Installing the feature and starting/stopping/enabling the service
are confirm-gated and need admin, same as every other state-changing
tool here - an open sshd is a real inbound attack surface.
"""

import subprocess
import os
import re
from typing import Dict

_SERVICE_NAME = "sshd"


class SshManager:
    """Inspect and control the OpenSSH Server feature/service on this machine."""

    def _run(self, cmd: list, timeout: float = 30.0) -> Dict:
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

    def _run_ps(self, script: str, timeout: float = 60.0) -> Dict:
        return self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_feature_status(self) -> Dict:
        """Check whether the OpenSSH Server optional Windows feature is installed."""
        result = self._run_ps(
            "Get-WindowsCapability -Online -Name OpenSSH.Server* | Select-Object Name, State | ConvertTo-Csv -NoTypeInformation"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Get-WindowsCapability failed")}
        lines = [l for l in result["stdout"].splitlines() if l.strip()]
        if len(lines) < 2:
            return {"installed": False}
        row = lines[1].split(",")
        state = row[1].strip('"') if len(row) > 1 else "Unknown"
        return {"installed": state == "Installed", "state": state}

    def install_feature(self, confirm: bool = False) -> Dict:
        """Install the OpenSSH Server optional Windows feature. Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will install the OpenSSH Server Windows feature (does not start it yet).",
            }
        result = self._run_ps("Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Add-WindowsCapability failed")}
        return {"success": True, "message": "OpenSSH Server feature installed."}

    def uninstall_feature(self, confirm: bool = False) -> Dict:
        """Remove the OpenSSH Server optional Windows feature entirely. Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will REMOVE the OpenSSH Server feature and stop any inbound SSH access.",
            }
        result = self._run_ps("Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Remove-WindowsCapability failed")}
        return {"success": True, "message": "OpenSSH Server feature removed."}

    def get_service_status(self) -> Dict:
        """Check the sshd service's run state and startup type."""
        result = self._run(["sc", "query", _SERVICE_NAME])
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "running": False,
                "installed": False,
                "note": "sshd service not found - feature may not be installed.",
            }
        state_m = re.search(r"STATE\s+:\s+\d+\s+(\w+)", result["stdout"])
        cfg = self._run(["sc", "qc", _SERVICE_NAME])
        start_type_m = re.search(r"START_TYPE\s+:\s+\d+\s+(\w+)", cfg["stdout"]) if cfg.get("success") else None
        return {
            "installed": True,
            "state": state_m.group(1) if state_m else "UNKNOWN",
            "running": bool(state_m and state_m.group(1) == "RUNNING"),
            "start_type": start_type_m.group(1) if start_type_m else "UNKNOWN",
        }

    def start_service(self, confirm: bool = False) -> Dict:
        """Start the sshd service (accept inbound SSH connections now). Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will start the sshd service - this machine will begin accepting inbound SSH connections.",
            }
        result = self._run(["net", "start", _SERVICE_NAME])
        if "error" in result:
            return result
        if not result["success"] and "already been started" not in (result["stdout"] + result["stderr"]).lower():
            return {"error": self._admin_hint(result["stderr"] or "net start sshd failed")}
        return {"success": True, "message": "sshd service started."}

    def stop_service(self, confirm: bool = False) -> Dict:
        """Stop the sshd service (reject new inbound SSH connections). Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": "This will stop the sshd service - existing sessions may drop and no new inbound SSH will be accepted.",
            }
        result = self._run(["net", "stop", _SERVICE_NAME])
        if "error" in result:
            return result
        if not result["success"] and "not started" not in (result["stdout"] + result["stderr"]).lower():
            return {"error": self._admin_hint(result["stderr"] or "net stop sshd failed")}
        return {"success": True, "message": "sshd service stopped."}

    def set_start_type(self, auto_start: bool, confirm: bool = False) -> Dict:
        """Set whether sshd starts automatically on boot. Confirm-gated, needs admin."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set sshd to {'start automatically' if auto_start else 'require manual/no auto start'} on boot.",
            }
        result = self._run(["sc", "config", _SERVICE_NAME, "start=", "auto" if auto_start else "demand"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "sc config failed")}
        return {"success": True, "auto_start": auto_start}

    def list_authorized_keys(self, username: str) -> Dict:
        """List public keys currently authorized for inbound SSH for a Windows username."""
        home = os.path.expanduser(f"~{username}") if username != os.environ.get("USERNAME") else os.path.expanduser("~")
        path = os.path.join(home, ".ssh", "authorized_keys")
        if not os.path.exists(path):
            return {"keys": [], "count": 0, "path": path}
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
            return {"keys": lines, "count": len(lines), "path": path}
        except Exception as e:
            return {"error": str(e)}

    def add_authorized_key(self, username: str, public_key: str, confirm: bool = False) -> Dict:
        """Append a public key to a user's authorized_keys for inbound SSH. Confirm-gated -
        this is granting someone passwordless SSH access to this account."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will grant SSH access to '{username}' via a new authorized key.",
            }
        home = os.path.expanduser(f"~{username}") if username != os.environ.get("USERNAME") else os.path.expanduser("~")
        ssh_dir = os.path.join(home, ".ssh")
        try:
            os.makedirs(ssh_dir, exist_ok=True)
            path = os.path.join(ssh_dir, "authorized_keys")
            with open(path, "a", encoding="utf-8") as f:
                f.write(public_key.strip() + "\n")
            return {"success": True, "path": path}
        except Exception as e:
            return {"error": str(e)}
