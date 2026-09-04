"""Windows Firewall rules
=======================
Query firewall status and manage allow/block rules via `netsh
advfirewall`. Rule changes need admin rights (netsh will report that
clearly if not elevated).

Renamed from firewall/firewall.py (FirewallTools) as part of Phase 8's
windows/ restructure. Only windows/__init__.py imported the old
module, so this is a clean rename. Adds add_block_rule alongside the
existing add_allow_rule, for self-management use cases like blocking
a specific app's network access.
"""

import subprocess
from typing import Dict


def _admin_aware_error(base_error: str) -> str:
    """Appends a clear, actionable hint when the likely cause of a
    netsh failure is that Ultron isn't running elevated - replaces the
    old generic "(try running as admin)" suffix with something that
    actually tells the user how to fix it (windows/system_info/admin.py)."""
    try:
        from windows.system_info.admin import is_admin, permission_denied_hint

        if not is_admin():
            return base_error + permission_denied_hint("Firewall rule changes")
    except Exception:
        from core.error_trace import log_swallowed as _lsw

        _lsw("windows.firewall.rules._admin_aware_error")
    return base_error


class FirewallRules:
    """Query/manage Windows Firewall via netsh advfirewall."""

    def get_firewall_status(self) -> Dict:
        """Get on/off status for domain, private, and public profiles."""
        try:
            result = subprocess.run(
                ["netsh", "advfirewall", "show", "allprofiles", "state"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "Failed to query firewall status"}
            return {"raw_output": result.stdout.strip()}
        except FileNotFoundError:
            return {"error": "netsh not found - firewall control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def list_rules(self, name_filter: str = None) -> Dict:
        """List firewall rules, optionally filtered by a name substring."""
        try:
            cmd = ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode != 0:
                return {"error": result.stderr.strip() or "Failed to list firewall rules"}
            output = result.stdout
            if name_filter:
                blocks = output.split("\n\n")
                output = "\n\n".join(b for b in blocks if name_filter.lower() in b.lower())
            return {"raw_output": output.strip()[:6000]}
        except FileNotFoundError:
            return {"error": "netsh not found - firewall control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def add_allow_rule(self, rule_name: str, program_path: str = None, port: int = None, protocol: str = "TCP") -> Dict:
        """Add an inbound allow rule, either for a program path or a port. Needs admin rights."""
        try:
            cmd = ["netsh", "advfirewall", "firewall", "add", "rule", f"name={rule_name}", "dir=in", "action=allow"]
            if program_path:
                cmd.append(f"program={program_path}")
            elif port:
                cmd.append(f"protocol={protocol}")
                cmd.append(f"localport={port}")
            else:
                return {"error": "Provide either program_path or port"}
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return {"success": True, "rule_name": rule_name}
            return {"error": _admin_aware_error(result.stderr.strip() or result.stdout.strip() or "Failed to add rule")}
        except FileNotFoundError:
            return {"error": "netsh not found - firewall control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def add_block_rule(
        self, rule_name: str, program_path: str = None, port: int = None, protocol: str = "TCP", direction: str = "out"
    ) -> Dict:
        """Add a block rule (default: outbound), either for a program path or a port.
        Useful for cutting a specific app's network access. Needs admin rights."""
        if direction not in ("in", "out"):
            return {"error": "direction must be 'in' or 'out'"}
        try:
            cmd = [
                "netsh",
                "advfirewall",
                "firewall",
                "add",
                "rule",
                f"name={rule_name}",
                f"dir={direction}",
                "action=block",
            ]
            if program_path:
                cmd.append(f"program={program_path}")
            elif port:
                cmd.append(f"protocol={protocol}")
                cmd.append(f"localport={port}")
            else:
                return {"error": "Provide either program_path or port"}
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return {"success": True, "rule_name": rule_name, "direction": direction}
            return {"error": _admin_aware_error(result.stderr.strip() or result.stdout.strip() or "Failed to add rule")}
        except FileNotFoundError:
            return {"error": "netsh not found - firewall control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}

    def remove_rule(self, rule_name: str, confirm: bool = False) -> Dict:
        """Remove a firewall rule by name. Needs admin rights. Safety-gated: needs confirm=true."""
        if not confirm:
            return {"error": f"This will remove firewall rule '{rule_name}'. Call again with confirm=true to proceed."}
        try:
            result = subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return {"success": True, "removed": rule_name}
            return {
                "error": _admin_aware_error(result.stderr.strip() or result.stdout.strip() or "Failed to remove rule")
            }
        except FileNotFoundError:
            return {"error": "netsh not found - firewall control is only available on Windows"}
        except Exception as e:
            return {"error": str(e)}
