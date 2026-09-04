"""Firewall Manager
====================
Windows Defender Firewall control via `netsh advfirewall` - profile
on/off state, rule listing, adding/removing custom rules, and quick
block/allow-a-program helpers. Needs admin for anything that changes
state; reads (status, list_rules) work without it.

Every state-changing method is confirm-gated - turning the firewall
off or adding an overly-broad allow rule is a real exposure risk, and
the preview always spells out exactly what will change.
"""

import subprocess
import re
from typing import Dict, Optional

_PROFILES = {"domain", "private", "public"}


class FirewallManager:
    """Inspect and control Windows Defender Firewall via netsh advfirewall."""

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
        if err and ("denied" in err.lower() or "not authorized" in err.lower() or "elevat" in err.lower()):
            return err + " - this needs ULTRON running as Administrator."
        return err

    def get_firewall_status(self, profile: Optional[str] = None) -> Dict:
        """Firewall on/off state for one profile (domain/private/public)
        or all profiles if omitted."""
        args = ["advfirewall", "show"]
        args.append(profile if profile and profile in _PROFILES else "allprofiles")
        result = self._run(args)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        profile_names = re.findall(r"(\w+ Profile Settings):", result["stdout"])
        on_off = re.findall(r"State\s+(ON|OFF)", result["stdout"])
        states = dict(zip(profile_names, on_off))
        return {"success": True, "raw": result["stdout"], "states": states}

    def enable_firewall(self, profile: str = "allprofiles", confirm: bool = False) -> Dict:
        """Turn the firewall on for a profile (or all). Needs admin.
        Confirm-gated."""
        if profile != "allprofiles" and profile not in _PROFILES:
            return {"error": f"profile must be one of {sorted(_PROFILES)} or 'allprofiles'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would turn the firewall ON for profile: {profile}.",
                "message": "Call again with confirm=true to enable.",
            }
        result = self._run(["advfirewall", "set", profile, "state", "on"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "profile": profile,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def disable_firewall(self, profile: str = "allprofiles", confirm: bool = False) -> Dict:
        """Turn the firewall off for a profile (or all). Needs admin.
        Confirm-gated - this is a real exposure risk, especially on a
        'public' profile."""
        if profile != "allprofiles" and profile not in _PROFILES:
            return {"error": f"profile must be one of {sorted(_PROFILES)} or 'allprofiles'"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would turn the firewall OFF for profile: {profile}. This "
                f"exposes the machine to unsolicited inbound traffic on that profile.",
                "message": "Call again with confirm=true to disable.",
            }
        result = self._run(["advfirewall", "set", profile, "state", "off"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "profile": profile,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def list_rules(self, name_filter: Optional[str] = None) -> Dict:
        """List firewall rules, optionally filtered by a name substring
        (netsh only supports exact name= or 'all')."""
        args = ["advfirewall", "firewall", "show", "rule", f"name={name_filter}" if name_filter else "name=all"]
        result = self._run(args, timeout=30.0)
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        rules = []
        current = {}
        for line in result["stdout"].splitlines():
            if not line.strip():
                if current:
                    rules.append(current)
                    current = {}
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                current[key.strip().lower().replace(" ", "_")] = val.strip()
        if current:
            rules.append(current)
        return {"success": True, "count": len(rules), "rules": rules}

    def add_rule(
        self,
        name: str,
        direction: str,
        action: str,
        protocol: str = "TCP",
        local_port: Optional[str] = None,
        program: Optional[str] = None,
        confirm: bool = False,
    ) -> Dict:
        """Add a custom firewall rule. direction: 'in'|'out'. action:
        'allow'|'block'. protocol: TCP/UDP/ICMPv4/any. local_port: a port
        number, range 'start-end', or omit for any. program: absolute
        path to restrict the rule to one executable. Needs admin.
        Confirm-gated."""
        if direction not in ("in", "out"):
            return {"error": "direction must be 'in' or 'out'"}
        if action not in ("allow", "block"):
            return {"error": "action must be 'allow' or 'block'"}
        if not confirm:
            desc = f"{action.upper()} {direction}bound {protocol}"
            if local_port:
                desc += f" port {local_port}"
            if program:
                desc += f" for {program}"
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would add firewall rule '{name}': {desc}.",
                "message": "Call again with confirm=true to add.",
            }
        args = [
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={name}",
            f"dir={direction}",
            f"action={action}",
            f"protocol={protocol}",
        ]
        if local_port:
            args.append(f"localport={local_port}")
        if program:
            args.append(f"program={program}")
        result = self._run(args)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "name": name,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def remove_rule(self, name: str, confirm: bool = False) -> Dict:
        """Delete a firewall rule by name (removes ALL rules with that
        exact name - netsh has no per-rule ID). Needs admin. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would delete firewall rule(s) named '{name}'.",
                "message": "Call again with confirm=true to delete.",
            }
        result = self._run(["advfirewall", "firewall", "delete", "rule", f"name={name}"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "name": name,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def set_rule_enabled(self, name: str, enabled: bool, confirm: bool = False) -> Dict:
        """Enable/disable an existing rule by name without deleting it.
        Needs admin. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would {'enable' if enabled else 'disable'} firewall rule '{name}'.",
                "message": "Call again with confirm=true to apply.",
            }
        result = self._run(
            ["advfirewall", "firewall", "set", "rule", f"name={name}", "new", f"enable={'yes' if enabled else 'no'}"]
        )
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "name": name,
            "enabled": enabled,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def block_program(self, program_path: str, confirm: bool = False) -> Dict:
        """Convenience: add a rule blocking both inbound and outbound
        traffic for a specific executable. Needs admin. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would block all network traffic (in+out) for {program_path}.",
                "message": "Call again with confirm=true to block.",
            }
        r_in = self.add_rule(
            f"ULTRON Block {program_path} (in)", "in", "block", protocol="any", program=program_path, confirm=True
        )
        r_out = self.add_rule(
            f"ULTRON Block {program_path} (out)", "out", "block", protocol="any", program=program_path, confirm=True
        )
        return {
            "success": r_in.get("success") and r_out.get("success"),
            "program": program_path,
            "inbound": r_in,
            "outbound": r_out,
        }

    def allow_program(self, program_path: str, confirm: bool = False) -> Dict:
        """Convenience: add a rule allowing both inbound and outbound
        traffic for a specific executable. Needs admin. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would allow all network traffic (in+out) for {program_path}.",
                "message": "Call again with confirm=true to allow.",
            }
        r_in = self.add_rule(
            f"ULTRON Allow {program_path} (in)", "in", "allow", protocol="any", program=program_path, confirm=True
        )
        r_out = self.add_rule(
            f"ULTRON Allow {program_path} (out)", "out", "allow", protocol="any", program=program_path, confirm=True
        )
        return {
            "success": r_in.get("success") and r_out.get("success"),
            "program": program_path,
            "inbound": r_in,
            "outbound": r_out,
        }
