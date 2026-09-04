"""Ethernet Manager
====================
Wired-adapter control via `netsh interface` - list adapters, read IP
config, enable/disable an adapter, switch between DHCP and a static IP,
set DNS servers, and flush the DNS resolver cache.

Adapter enable/disable and any IP/DNS change are confirm-gated - a wrong
static IP or the wrong adapter disabled can knock the machine off the
network. flush_dns is a harmless cache clear and is not gated.
"""

import subprocess
from typing import Dict, List, Optional


class EthernetManager:
    """Inspect and control wired network adapters via netsh interface."""

    def _run(self, args: list, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(["netsh"] + args, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": "netsh not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower()):
            return err + " - this may need ULTRON running as Administrator."
        return err

    def list_adapters(self) -> Dict:
        """List network interfaces with admin/connect state and type."""
        result = self._run(["interface", "show", "interface"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        adapters = []
        lines = result["stdout"].splitlines()
        for line in lines[3:]:  # skip header + column-title rows
            parts = line.split(None, 3)
            if len(parts) == 4:
                admin_state, connect_state, itype, name = parts
                adapters.append(
                    {
                        "name": name.strip(),
                        "admin_state": admin_state,
                        "connect_state": connect_state,
                        "type": itype,
                    }
                )
        return {"success": True, "adapters": adapters}

    def get_adapter_status(self, name: str) -> Dict:
        """Status for one named adapter, filtered from list_adapters()."""
        all_adapters = self.list_adapters()
        if "error" in all_adapters:
            return all_adapters
        for a in all_adapters["adapters"]:
            if a["name"].lower() == name.lower():
                return {"success": True, "adapter": a}
        return {"error": f"Adapter not found: {name}"}

    def enable_adapter(self, name: str, confirm: bool = False) -> Dict:
        """Enable a network adapter. Needs admin. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would enable adapter '{name}'.",
                "message": "Call again with confirm=true to enable.",
            }
        result = self._run(["interface", "set", "interface", name, "admin=enabled"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "adapter": name,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def disable_adapter(self, name: str, confirm: bool = False) -> Dict:
        """Disable a network adapter. Needs admin. Confirm-gated - can
        drop the connection ULTRON itself is running over."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would disable adapter '{name}' - this will drop its connection.",
                "message": "Call again with confirm=true to disable.",
            }
        result = self._run(["interface", "set", "interface", name, "admin=disabled"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "adapter": name,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def get_ip_config(self, name: Optional[str] = None) -> Dict:
        """Current IPv4 config (address/mask/gateway/DHCP status) for one
        adapter, or all adapters if name is omitted."""
        args = ["interface", "ip", "show", "config"]
        if name:
            args += [f"name={name}"]
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        return {"success": True, "raw": result["stdout"]}

    def set_static_ip(self, name: str, ip: str, subnet_mask: str, gateway: str, confirm: bool = False) -> Dict:
        """Assign a static IPv4 address to an adapter. Confirm-gated - a
        bad value here can cut off network access."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set '{name}' to static IP {ip}, mask {subnet_mask}, " f"gateway {gateway}.",
                "message": "Call again with confirm=true to apply.",
            }
        result = self._run(["interface", "ip", "set", "address", f"name={name}", "static", ip, subnet_mask, gateway])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "adapter": name,
            "ip": ip,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def set_dhcp(self, name: str, confirm: bool = False) -> Dict:
        """Switch an adapter back to DHCP (automatic IP). Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set '{name}' back to DHCP (automatic IP).",
                "message": "Call again with confirm=true to apply.",
            }
        result = self._run(["interface", "ip", "set", "address", f"name={name}", "dhcp"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "adapter": name,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def set_dns(self, name: str, dns_servers: List[str], confirm: bool = False) -> Dict:
        """Set static DNS server(s) for an adapter (first entry primary,
        rest added). Confirm-gated."""
        if not dns_servers:
            return {"error": "dns_servers must be a non-empty list"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set DNS for '{name}' to {', '.join(dns_servers)}.",
                "message": "Call again with confirm=true to apply.",
            }
        r1 = self._run(["interface", "ip", "set", "dns", f"name={name}", "static", dns_servers[0]])
        if "error" in r1:
            return r1
        errors = [] if r1["success"] else [r1["stderr"] or r1["stdout"]]
        for extra in dns_servers[1:]:
            r = self._run(["interface", "ip", "add", "dns", f"name={name}", extra, "index=2"])
            if "error" in r or not r.get("success"):
                errors.append(r.get("error") or r.get("stderr") or "add dns failed")
        return {
            "success": not errors,
            "adapter": name,
            "dns_servers": dns_servers,
            "errors": [self._admin_hint(e) for e in errors] or None,
        }

    def flush_dns(self) -> Dict:
        """Clear the local DNS resolver cache. Harmless - not confirm-gated."""
        try:
            result = subprocess.run(["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=10)
            return {"success": result.returncode == 0, "stdout": result.stdout.strip()}
        except FileNotFoundError:
            return {"error": "ipconfig not found - this is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}
