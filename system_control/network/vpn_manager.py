"""VPN Manager
==============
Windows' built-in VPN client (the one under Settings > Network > VPN),
controlled via PowerShell's VpnClient cmdlets for profile management and
`rasdial` for actual connect/disconnect. Third-party VPN apps (NordVPN,
ExpressVPN, corporate AnyConnect clients, etc.) are out of scope - those
run their own services and aren't reachable through this Windows-native
surface.

add/remove/connect/disconnect are all confirm-gated. connect_vpn in
particular warns when a password is passed inline: rasdial takes it as a
plain command-line argument, which is briefly visible to anything that
can list running processes on the machine - connecting with a saved
profile (no username/password passed) avoids that entirely.
"""

import subprocess
import json
from typing import Dict, Optional


class VpnManager:
    """List/add/remove Windows VPN connection profiles and connect/
    disconnect via rasdial."""

    def _run_ps(self, script: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
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
            return {"error": "powershell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _run_rasdial(self, args: list) -> Dict:
        try:
            result = subprocess.run(["rasdial"] + args, capture_output=True, text=True, timeout=25)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "rasdial not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def list_vpn_connections(self) -> Dict:
        """List Windows VPN connection profiles configured for this user."""
        result = self._run_ps("Get-VpnConnection | ConvertTo-Json -Depth 3")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Get-VpnConnection failed"}
        if not result["stdout"]:
            return {"success": True, "connections": []}
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse VPN connection list"}
        items = data if isinstance(data, list) else [data]
        return {
            "success": True,
            "connections": [
                {
                    "name": c.get("Name"),
                    "server": c.get("ServerAddress"),
                    "connection_status": c.get("ConnectionStatus"),
                    "tunnel_type": c.get("TunnelType"),
                }
                for c in items
            ],
        }

    def get_vpn_status(self, name: str) -> Dict:
        """Status for one named VPN connection."""
        all_conns = self.list_vpn_connections()
        if "error" in all_conns:
            return all_conns
        for c in all_conns["connections"]:
            if c["name"] and c["name"].lower() == name.lower():
                return {"success": True, "connection": c}
        return {"error": f"VPN connection not found: {name}"}

    def add_vpn_connection(
        self, name: str, server_address: str, tunnel_type: str = "Automatic", confirm: bool = False
    ) -> Dict:
        """Create a new Windows VPN profile. tunnel_type: Automatic, Pptp,
        L2tp, Sstp, or Ikev2. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would add VPN connection '{name}' -> {server_address} " f"(tunnel: {tunnel_type}).",
                "message": "Call again with confirm=true to add.",
            }
        script = (
            f"Add-VpnConnection -Name '{name}' -ServerAddress '{server_address}' " f"-TunnelType '{tunnel_type}' -Force"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        return {"success": result["success"], "name": name, "error": None if result["success"] else result["stderr"]}

    def remove_vpn_connection(self, name: str, confirm: bool = False) -> Dict:
        """Delete a Windows VPN profile. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove VPN connection '{name}'.",
                "message": "Call again with confirm=true to remove.",
            }
        result = self._run_ps(f"Remove-VpnConnection -Name '{name}' -Force")
        if "error" in result:
            return result
        return {"success": result["success"], "name": name, "error": None if result["success"] else result["stderr"]}

    def connect_vpn(
        self, name: str, username: Optional[str] = None, password: Optional[str] = None, confirm: bool = False
    ) -> Dict:
        """Connect a VPN profile via rasdial. Omit username/password to
        use the profile's saved credentials (recommended - see module
        docstring on why inline passwords are best avoided). Confirm-gated."""
        if not confirm:
            preview = f"Would connect to VPN '{name}'"
            preview += " using saved credentials." if not username else " with the given credentials."
            warn = None
            if password:
                warn = (
                    "Passing a password here means it briefly appears as a plain command-line "
                    "argument, visible to other processes that can list running tasks."
                )
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": preview,
                "warning": warn,
                "message": "Call again with confirm=true to connect.",
            }
        args = [name]
        if username:
            args.append(username)
        if password:
            args.append(password)
        result = self._run_rasdial(args)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "name": name,
            "error": None if result["success"] else (result["stdout"] or result["stderr"]),
        }

    def disconnect_vpn(self, name: str, confirm: bool = False) -> Dict:
        """Disconnect an active VPN connection via rasdial. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would disconnect VPN '{name}'.",
                "message": "Call again with confirm=true to disconnect.",
            }
        result = self._run_rasdial([name, "/disconnect"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "name": name,
            "error": None if result["success"] else (result["stdout"] or result["stderr"]),
        }
