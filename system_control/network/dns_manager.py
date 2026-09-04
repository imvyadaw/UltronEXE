"""DNS Manager
==============
DNS-related tools that sit above the single-adapter DNS-server setting
already covered by network/ethernet_manager.py (set_dns/flush_dns
there): the hosts file (manual name -> IP overrides), ad-hoc lookups
for troubleshooting, the per-adapter DNS suffix search list, and
Windows' system-wide DNS-over-HTTPS encryption setting (`netsh dns`,
Windows 11 22H2+).

Hosts-file edits and the DoH toggle are confirm-gated - a bad hosts
entry silently redirects a domain for every app on the machine, and
Notepad-adjacent tools should always preview a destructive edit before
writing it.
"""

import subprocess
import re
from pathlib import Path
from typing import Dict

_HOSTS_PATH = Path(r"C:\Windows\System32\drivers\etc\hosts")


class DnsManager:
    """Hosts file management, DNS lookups, and DNS-over-HTTPS control."""

    def _run(self, args: list, timeout: float = 15.0) -> Dict:
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

    # -- hosts file --------------------------------------------------

    def list_hosts_entries(self) -> Dict:
        """Read and parse the current hosts file (skips comments/blanks)."""
        if not _HOSTS_PATH.exists():
            return {"error": f"hosts file not found at {_HOSTS_PATH}"}
        try:
            entries = []
            for line in _HOSTS_PATH.read_text(errors="ignore").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split()
                if len(parts) >= 2:
                    entries.append({"ip": parts[0], "hostname": parts[1]})
            return {"success": True, "entries": entries, "count": len(entries)}
        except Exception as e:
            return {"error": str(e)}

    def add_hosts_entry(self, ip: str, hostname: str, confirm: bool = False) -> Dict:
        """Append an IP -> hostname override to the hosts file. Needs
        admin. Confirm-gated - redirects that hostname for every app on
        the machine until removed."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would add hosts entry: {ip} {hostname} (redirects that " f"hostname system-wide).",
                "message": "Call again with confirm=true to add.",
            }
        try:
            with open(_HOSTS_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n{ip}\t{hostname}\n")
            return {"success": True, "ip": ip, "hostname": hostname}
        except PermissionError:
            return {"error": "Permission denied writing hosts file - run ULTRON as Administrator."}
        except Exception as e:
            return {"error": str(e)}

    def remove_hosts_entry(self, hostname: str, confirm: bool = False) -> Dict:
        """Remove all hosts-file lines for a given hostname. Needs admin.
        Confirm-gated."""
        if not _HOSTS_PATH.exists():
            return {"error": f"hosts file not found at {_HOSTS_PATH}"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would remove all hosts entries for '{hostname}'.",
                "message": "Call again with confirm=true to remove.",
            }
        try:
            lines = _HOSTS_PATH.read_text(errors="ignore").splitlines()
            kept, removed = [], 0
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith("#") and re.search(rf"\b{re.escape(hostname)}\b", stripped):
                    removed += 1
                    continue
                kept.append(line)
            _HOSTS_PATH.write_text("\n".join(kept) + "\n", encoding="utf-8")
            return {"success": True, "hostname": hostname, "lines_removed": removed}
        except PermissionError:
            return {"error": "Permission denied writing hosts file - run ULTRON as Administrator."}
        except Exception as e:
            return {"error": str(e)}

    # -- lookups / suffixes -------------------------------------------

    def lookup(self, hostname: str, record_type: str = "A") -> Dict:
        """Resolve a hostname via nslookup - useful to check what a name
        currently resolves to (e.g. after a hosts-file change)."""
        result = self._run(["nslookup", f"-type={record_type}", hostname])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "nslookup failed"}
        return {"success": True, "hostname": hostname, "record_type": record_type, "raw": result["stdout"]}

    def get_dns_suffix_list(self) -> Dict:
        """Get the DNS suffix search list applied when resolving
        unqualified hostnames."""
        result = self._run(["netsh", "interface", "ip", "show", "dnsservers"])
        if "error" in result:
            return result
        return {"success": True, "raw": result["stdout"]}

    # -- DNS-over-HTTPS (Windows 11 22H2+) -----------------------------

    def get_doh_settings(self) -> Dict:
        """Current system DNS-over-HTTPS encryption state (netsh dns
        show encryption). Only present on Windows 11 22H2+."""
        result = self._run(["netsh", "dns", "show", "encryption"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Not supported on this Windows build")}
        return {"success": True, "raw": result["stdout"]}

    def set_doh(
        self,
        server_ip: str,
        doh_template: str,
        auto_upgrade: bool = True,
        udp_fallback: bool = False,
        confirm: bool = False,
    ) -> Dict:
        """Configure DNS-over-HTTPS for a specific resolver IP (e.g.
        1.1.1.1 with template https://cloudflare-dns.com/dns-query).
        Needs admin, Windows 11 22H2+. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would set DoH for resolver {server_ip} -> {doh_template} "
                f"(auto_upgrade={auto_upgrade}, udp_fallback={udp_fallback}).",
                "message": "Call again with confirm=true to apply.",
            }
        args = [
            "netsh",
            "dns",
            "add",
            "encryption",
            f"server={server_ip}",
            f"dohtemplate={doh_template}",
            f"autoupgrade={'yes' if auto_upgrade else 'no'}",
            f"udpfallback={'yes' if udp_fallback else 'no'}",
        ]
        result = self._run(args)
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "server_ip": server_ip,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }
