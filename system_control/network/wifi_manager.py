"""Wi-Fi Manager
================
Thin wrapper over `netsh wlan` - list nearby networks, saved profiles,
current connection, connect/disconnect, forget a saved profile, and
enable/disable the Wi-Fi adapter outright.

get_saved_password reveals a stored Wi-Fi key in clear text (netsh wlan
... key=clear) - confirm-gated on that basis alone, same as any other
tool that exposes a secret. connect/disconnect/forget/enable/disable are
confirm-gated as state-changing; listing/status reads are not.
"""

import subprocess
import re
from typing import Dict


class WifiManager:
    """Inspect and control Wi-Fi networks/profiles via netsh wlan."""

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

    def list_available_networks(self) -> Dict:
        """List nearby Wi-Fi networks (SSID, signal, auth type)."""
        result = self._run(["wlan", "show", "networks", "mode=bssid"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        networks = []
        current = None
        for line in result["stdout"].splitlines():
            line = line.strip()
            m = re.match(r"SSID \d+ : (.*)", line)
            if m:
                if current:
                    networks.append(current)
                current = {"ssid": m.group(1), "signal": None, "auth": None}
            elif current is not None:
                m2 = re.match(r"Signal\s*:\s*(.*)", line)
                if m2:
                    current["signal"] = m2.group(1)
                m3 = re.match(r"Authentication\s*:\s*(.*)", line)
                if m3:
                    current["auth"] = m3.group(1)
        if current:
            networks.append(current)
        return {"success": True, "networks": networks}

    def list_saved_profiles(self) -> Dict:
        """List Wi-Fi profiles saved on this machine."""
        result = self._run(["wlan", "show", "profiles"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        profiles = re.findall(r"All User Profile\s*:\s*(.+)", result["stdout"])
        return {"success": True, "profiles": [p.strip() for p in profiles]}

    def get_current_connection(self) -> Dict:
        """Current Wi-Fi interface state (SSID, signal, state, radio)."""
        result = self._run(["wlan", "show", "interfaces"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "netsh failed")}
        info = {}
        for line in result["stdout"].splitlines():
            if ":" not in line:
                continue
            key, _, val = line.strip().partition(":")
            key, val = key.strip(), val.strip()
            if key in ("SSID", "State", "Signal", "Radio type", "Channel", "Authentication"):
                info[key.lower().replace(" ", "_")] = val
        return {"success": True, "connection": info}

    def get_saved_password(self, profile: str, confirm: bool = False) -> Dict:
        """Reveal the stored key for a saved Wi-Fi profile in clear text.
        Confirm-gated - exposes a secret."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would reveal the saved password for Wi-Fi profile '{profile}'.",
                "message": "Call again with confirm=true to reveal.",
            }
        result = self._run(["wlan", "show", "profile", f"name={profile}", "key=clear"])
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": self._admin_hint(result["stderr"] or "Profile not found")}
        m = re.search(r"Key Content\s*:\s*(.+)", result["stdout"])
        return {"success": True, "profile": profile, "password": m.group(1).strip() if m else None}

    def connect(self, ssid: str, confirm: bool = False) -> Dict:
        """Connect to a Wi-Fi network by SSID (must already be a saved
        profile, or be open/broadcasting). Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would connect to Wi-Fi network '{ssid}'.",
                "message": "Call again with confirm=true to connect.",
            }
        result = self._run(["wlan", "connect", f"name={ssid}"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "ssid": ssid,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def disconnect(self, confirm: bool = False) -> Dict:
        """Disconnect from the current Wi-Fi network. Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would disconnect from Wi-Fi.",
                "message": "Call again with confirm=true to disconnect.",
            }
        result = self._run(["wlan", "disconnect"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "error": None if result["success"] else self._admin_hint(result["stderr"]),
        }

    def forget_network(self, profile: str, confirm: bool = False) -> Dict:
        """Delete a saved Wi-Fi profile (forgets the network and its
        password). Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would forget saved Wi-Fi network '{profile}' (deletes its saved password too).",
                "message": "Call again with confirm=true to forget.",
            }
        result = self._run(["wlan", "delete", "profile", f"name={profile}"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "profile": profile,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }

    def set_wifi_enabled(self, enabled: bool, interface: str = "Wi-Fi", confirm: bool = False) -> Dict:
        """Turn the Wi-Fi adapter on/off entirely (netsh interface admin
        state). Needs admin. Confirm-gated - disabling it will drop any
        active Wi-Fi connection."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would turn Wi-Fi adapter '{interface}' {'on' if enabled else 'off'}.",
                "message": "Call again with confirm=true to apply.",
            }
        result = self._run(
            ["interface", "set", "interface", interface, f"admin={'enabled' if enabled else 'disabled'}"]
        )
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "interface": interface,
            "enabled": enabled,
            "error": None if result["success"] else self._admin_hint(result["stderr"] or result["stdout"]),
        }
