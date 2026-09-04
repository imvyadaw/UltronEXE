"""IP Config
============
Cross-adapter IP overview and the routing table - the layer above
network/ethernet_manager.py (which sets one adapter's own address/DHCP/
DNS). This module answers "what does the whole machine's IP picture
look like" (get_full_ip_config, IPv6 included) and manages static
routes, plus adding/removing *extra* IP addresses on an adapter beyond
its primary one.

Route and secondary-address changes are confirm-gated - a bad route can
silently blackhole traffic to a whole subnet.
"""

import subprocess
from typing import Dict, Optional


class IpConfig:
    """Whole-machine IP overview, routing table, and secondary IP
    addresses, via netsh/ipconfig."""

    def _run(self, args: list, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        except FileNotFoundError:
            return {"error": f"{args[0]} not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _admin_hint(self, err: str) -> str:
        if err and ("denied" in err.lower() or "not authorized" in err.lower()):
            return err + " - this may need ULTRON running as Administrator."
        return err

    def get_full_ip_config(self) -> Dict:
        """Full ipconfig /all output - every adapter, IPv4+IPv6, DNS,
        DHCP lease info."""
        result = self._run(["ipconfig", "/all"])
        if "error" in result:
            return result
        return {"success": True, "raw": result["stdout"]}

    def get_public_ip_hint(self) -> Dict:
        """Note: determining the machine's public/external IP requires an
        outbound request to a third-party service, which this local
        system-control module intentionally doesn't make. Use a
        web-search-capable tool instead if that's what's needed."""
        return {
            "success": True,
            "note": "Public IP lookup needs an external service call - not something this "
            "local system-control module does. Ask for a web lookup instead.",
        }

    def get_routing_table(self) -> Dict:
        """Current IPv4 routing table."""
        result = self._run(["route", "print", "-4"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "route print failed"}
        return {"success": True, "raw": result["stdout"]}

    def add_route(
        self,
        destination: str,
        mask: str,
        gateway: str,
        metric: Optional[int] = None,
        persistent: bool = True,
        confirm: bool = False,
    ) -> Dict:
        """Add a static route. persistent=True survives reboot (route
        add -p); False is session-only. Needs admin for persistent
        routes. Confirm-gated - a wrong route can blackhole traffic to
        that subnet."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would add {'persistent ' if persistent else ''}route: "
                f"{destination} mask {mask} via {gateway}"
                f"{f' metric {metric}' if metric else ''}.",
                "message": "Call again with confirm=true to add.",
            }
        args = ["route"]
        if persistent:
            args.append("-p")
        args += ["add", destination, "mask", mask, gateway]
        if metric:
            args += ["metric", str(metric)]
        result = self._run(args)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "destination": destination,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def remove_route(self, destination: str, confirm: bool = False) -> Dict:
        """Delete a static route by destination. Needs admin for
        persistent routes. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove route to {destination}.",
                "message": "Call again with confirm=true to remove.",
            }
        result = self._run(["route", "delete", destination])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "destination": destination,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def add_secondary_ip(self, adapter: str, ip: str, subnet_mask: str, confirm: bool = False) -> Dict:
        """Add an extra IPv4 address to an adapter that already has a
        primary one (netsh ...ip add address). Needs admin. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would add secondary IP {ip}/{subnet_mask} to adapter '{adapter}'.",
                "message": "Call again with confirm=true to add.",
            }
        result = self._run(["netsh", "interface", "ip", "add", "address", f"name={adapter}", ip, subnet_mask])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "adapter": adapter,
            "ip": ip,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def remove_secondary_ip(self, adapter: str, ip: str, confirm: bool = False) -> Dict:
        """Remove a secondary IPv4 address from an adapter. Needs admin.
        Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove secondary IP {ip} from adapter '{adapter}'.",
                "message": "Call again with confirm=true to remove.",
            }
        result = self._run(["netsh", "interface", "ip", "delete", "address", f"name={adapter}", ip])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "adapter": adapter,
            "ip": ip,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }
