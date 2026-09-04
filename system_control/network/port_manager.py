"""Port Manager
================
Local-port inspection and control - what's listening on a port and
which process owns it (`netstat`/PowerShell Get-NetTCPConnection),
killing the owning process, and port-forwarding rules via
`netsh interface portproxy`. Distinct from firewall_manager (which
allows/blocks traffic by rule, not by inspecting live sockets) and
from system_control/process (general process management, not
port-scoped) - this module is specifically the port <-> process/
forward mapping layer.

Listing/inspecting ports and forwards are plain reads. Killing the
process on a port and adding/removing a portproxy forward are
confirm-gated as state-changing, same as every other destructive
tool in this codebase.
"""

import subprocess
import re
from typing import Dict


class PortManager:
    """Inspect local listening ports and control port-forwarding rules."""

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

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def list_listening_ports(self) -> Dict:
        """List all TCP ports currently in LISTENING state, with owning PID."""
        result = self._run(["netstat", "-ano", "-p", "TCP"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netstat failed")}
        ports = []
        for line in result["stdout"].splitlines():
            m = re.match(r"\s*TCP\s+(\S+):(\d+)\s+(\S+)\s+LISTENING\s+(\d+)", line)
            if m:
                ports.append(
                    {
                        "local_address": m.group(1),
                        "port": int(m.group(2)),
                        "pid": int(m.group(4)),
                    }
                )
        return {"ports": ports, "count": len(ports)}

    def get_process_on_port(self, port: int) -> Dict:
        """Find which process (PID + name) owns a given local port."""
        listed = self.list_listening_ports()
        if "error" in listed:
            return listed
        matches = [p for p in listed["ports"] if p["port"] == port]
        if not matches:
            return {"error": f"No process is listening on port {port}."}
        results = []
        for m in matches:
            name_result = self._run(["tasklist", "/FI", f"PID eq {m['pid']}", "/FO", "CSV", "/NH"])
            name = None
            if name_result.get("success") and name_result["stdout"]:
                parts = name_result["stdout"].split(",")
                if parts:
                    name = parts[0].strip('"')
            results.append({**m, "process_name": name})
        return {"port": port, "matches": results}

    def kill_process_on_port(self, port: int, confirm: bool = False) -> Dict:
        """Kill the process(es) currently listening on a given port. Confirm-gated."""
        info = self.get_process_on_port(port)
        if "error" in info:
            return info
        if not confirm:
            names = ", ".join(
                f"{m.get('process_name') or 'PID ' + str(m['pid'])} (PID {m['pid']})" for m in info["matches"]
            )
            return {
                "requires_confirmation": True,
                "preview": f"This will forcibly kill: {names} - currently listening on port {port}.",
            }
        killed, errors = [], []
        for m in info["matches"]:
            result = self._run(["taskkill", "/PID", str(m["pid"]), "/F"])
            if result.get("success"):
                killed.append(m["pid"])
            else:
                errors.append({"pid": m["pid"], "error": self._admin_hint(result.get("stderr") or "taskkill failed")})
        return {"success": len(errors) == 0, "killed_pids": killed, "errors": errors or None}

    def list_port_forwards(self) -> Dict:
        """List active `netsh interface portproxy` forwarding rules."""
        result = self._run(["netsh", "interface", "portproxy", "show", "all"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh portproxy show failed")}
        forwards = []
        for line in result["stdout"].splitlines():
            m = re.match(r"\s*(\S+)\s+(\d+)\s+(\S+)\s+(\d+)\s*$", line)
            if m and m.group(1) not in ("Address", "---------------"):
                forwards.append(
                    {
                        "listen_address": m.group(1),
                        "listen_port": int(m.group(2)),
                        "connect_address": m.group(3),
                        "connect_port": int(m.group(4)),
                    }
                )
        return {"forwards": forwards, "count": len(forwards)}

    def add_port_forward(
        self,
        listen_port: int,
        connect_port: int,
        listen_address: str = "0.0.0.0",
        connect_address: str = "127.0.0.1",
        confirm: bool = False,
    ) -> Dict:
        """Add a port-forwarding rule (e.g. expose a local dev server on another
        port/interface). Confirm-gated - this changes what's reachable on this
        machine's network interfaces."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will forward {listen_address}:{listen_port} -> {connect_address}:{connect_port}.",
            }
        result = self._run(
            [
                "netsh",
                "interface",
                "portproxy",
                "add",
                "v4tov4",
                f"listenport={listen_port}",
                f"listenaddress={listen_address}",
                f"connectport={connect_port}",
                f"connectaddress={connect_address}",
            ]
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh portproxy add failed")}
        return {
            "success": True,
            "listen": f"{listen_address}:{listen_port}",
            "connect": f"{connect_address}:{connect_port}",
        }

    def remove_port_forward(self, listen_port: int, listen_address: str = "0.0.0.0", confirm: bool = False) -> Dict:
        """Remove a port-forwarding rule by its listen address/port. Confirm-gated."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will remove the port forward listening on {listen_address}:{listen_port}.",
            }
        result = self._run(
            [
                "netsh",
                "interface",
                "portproxy",
                "delete",
                "v4tov4",
                f"listenport={listen_port}",
                f"listenaddress={listen_address}",
            ]
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh portproxy delete failed")}
        return {"success": True, "removed": f"{listen_address}:{listen_port}"}

    def is_port_open_locally(self, port: int, host: str = "127.0.0.1", timeout: float = 2.0) -> Dict:
        """Quick TCP connect check - is something accepting connections on host:port."""
        import socket

        try:
            with socket.create_connection((host, port), timeout=timeout):
                return {"open": True, "host": host, "port": port}
        except Exception:
            return {"open": False, "host": host, "port": port}
