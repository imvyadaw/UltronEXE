"""Remote Desktop Manager
==========================
Windows Remote Desktop (RDP host) control - checks/toggles the
fDenyTSConnections registry flag that gates whether this machine
accepts incoming RDP sessions, manages the matching "Remote Desktop"
Windows Defender Firewall rule group, and lists currently connected
RDP sessions via `query user`. Distinct from system_control/network's
vpn_manager (outbound VPN tunnels) and from the top-level networking/
package (protocol clients this machine initiates) - this is about
*inbound* remote-control access to this machine.

All reads (get_status, list_sessions) work without admin. Enabling/
disabling RDP requires admin and is confirm-gated, same as every
other state-changing tool here - turning this on is a genuine
attack-surface change.
"""

import subprocess
import re
from typing import Dict

_REG_PATH = r"HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server"
_REG_VALUE = "fDenyTSConnections"


class RemoteDesktop:
    """Inspect and control inbound Remote Desktop (RDP) access to this machine."""

    def _run(self, cmd: list, timeout: float = 15.0) -> Dict:
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

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_status(self) -> Dict:
        """Check whether inbound Remote Desktop connections are currently allowed."""
        result = self._run(["reg", "query", _REG_PATH, "/v", _REG_VALUE])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "reg query failed")}
        m = re.search(r"0x([0-9A-Fa-f]+)", result["stdout"])
        if not m:
            return {"error": "Could not parse registry value."}
        deny_flag = int(m.group(1), 16)
        # fDenyTSConnections: 0 = RDP allowed, 1 = RDP denied
        return {"rdp_enabled": deny_flag == 0}

    def set_enabled(self, enabled: bool, confirm: bool = False) -> Dict:
        """Enable or disable inbound Remote Desktop connections. Confirm-gated
        and needs admin - this changes this machine's remote-access attack
        surface."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": (
                    "This will ALLOW incoming Remote Desktop connections to this machine "
                    "(and open the matching firewall rule group)."
                    if enabled
                    else "This will BLOCK incoming Remote Desktop connections to this machine "
                    "(and close the matching firewall rule group)."
                ),
            }
        deny_value = "0" if enabled else "1"
        result = self._run(["reg", "add", _REG_PATH, "/v", _REG_VALUE, "/t", "REG_DWORD", "/d", deny_value, "/f"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "reg add failed")}
        fw = self._run(
            [
                "netsh",
                "advfirewall",
                "firewall",
                "set",
                "rule",
                "group=remote desktop",
                "new",
                f"enable={'yes' if enabled else 'no'}",
            ]
        )
        fw_ok = "error" not in fw and fw.get("success")
        return {
            "success": True,
            "rdp_enabled": enabled,
            "firewall_rule_updated": fw_ok,
            "firewall_note": (
                None
                if fw_ok
                else "Registry flag was set, but the firewall rule group update failed - you may need to allow it manually."
            ),
        }

    def list_active_sessions(self) -> Dict:
        """List currently connected RDP (and console) sessions via `query user`."""
        result = self._run(["query", "user"])
        if "error" in result:
            return result
        if not result["success"]:
            if "No User exists" in (result["stderr"] or ""):
                return {"sessions": [], "count": 0}
            return {"error": self._admin_hint(result["stderr"] or "query user failed")}
        lines = result["stdout"].splitlines()
        sessions = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 4:
                sessions.append(
                    {
                        "username": parts[0].lstrip(">"),
                        "session_name": parts[1] if not parts[1].isdigit() else None,
                        "state": next((p for p in parts if p in ("Active", "Disc")), None),
                        "raw": line.strip(),
                    }
                )
        return {"sessions": sessions, "count": len(sessions)}

    def log_off_session(self, session_id: str, confirm: bool = False) -> Dict:
        """Force log off a specific RDP session by its numeric session ID. Confirm-gated."""
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will forcibly log off session ID {session_id}."}
        result = self._run(["logoff", str(session_id)])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "logoff failed")}
        return {"success": True, "logged_off_session": session_id}
