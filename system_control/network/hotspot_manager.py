"""Hotspot Manager
===================
Windows' mobile-hotspot / "hosted network" feature - share this
machine's internet connection over Wi-Fi via `netsh wlan
hostednetwork`. Distinct from network/wifi_manager.py, which connects
*to* networks rather than creating one.

Note: `netsh wlan hostednetwork` is the classic scriptable API and
still works on most Windows 10/11 builds, but some newer Wi-Fi drivers
only expose hotspot sharing through the Settings app's Mobile Hotspot
UI (no netsh equivalent) - if start_hotspot reports the adapter doesn't
support hosted networks, that's the likely reason, and the result says
so rather than failing silently.

configure/start/stop are all confirm-gated, and configure_hotspot's
preview never echoes the key back in plain sight for other tools to log.
"""

import subprocess
import re
from typing import Dict, Optional


class HotspotManager:
    """Configure and control Windows' hosted-network mobile hotspot via
    netsh wlan hostednetwork."""

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

    def _not_supported_hint(self, output: str) -> Optional[str]:
        if output and ("not supported" in output.lower() or "not started" in output.lower()):
            return (
                "This adapter/driver may not support the legacy hosted-network API - try "
                "Settings > Network & internet > Mobile hotspot instead."
            )
        return None

    def get_hotspot_status(self) -> Dict:
        """Current hosted-network status: whether it's supported,
        configured, and started, plus SSID/authentication if set."""
        result = self._run(["wlan", "show", "hostednetwork"])
        if "error" in result:
            return result
        out = result["stdout"]
        status = {}
        for line in out.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            status[key.strip().lower().replace(" ", "_")] = val.strip()
        return {"success": True, "status": status, "raw": out, "hint": self._not_supported_hint(out)}

    def configure_hotspot(self, ssid: str, key: str, confirm: bool = False) -> Dict:
        """Set the hotspot's SSID and passphrase (key must be 8-63
        characters, WPA2-PSK). Doesn't start it - call start_hotspot after.
        Confirm-gated; the key itself is never echoed back in the preview."""
        if len(key) < 8 or len(key) > 63:
            return {"error": "key must be 8-63 characters (WPA2-PSK requirement)"}
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": f"Would configure hotspot SSID '{ssid}' with a new passphrase.",
                "message": "Call again with confirm=true to configure.",
            }
        result = self._run(["wlan", "set", "hostednetwork", "mode=allow", f"ssid={ssid}", f"key={key}"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "ssid": ssid,
            "error": (
                None
                if result["success"]
                else (
                    self._not_supported_hint(result["stdout"] + result["stderr"])
                    or result["stderr"]
                    or result["stdout"]
                )
            ),
        }

    def start_hotspot(self, confirm: bool = False) -> Dict:
        """Start broadcasting the configured hotspot. Confirm-gated -
        makes this machine's connection reachable to anything that joins."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would start the mobile hotspot, making it joinable by nearby devices.",
                "message": "Call again with confirm=true to start.",
            }
        result = self._run(["wlan", "start", "hostednetwork"])
        if "error" in result:
            return result
        combined = result["stdout"] + result["stderr"]
        return {
            "success": result["success"],
            "started": result["success"],
            "error": (
                None
                if result["success"]
                else (self._not_supported_hint(combined) or result["stderr"] or result["stdout"])
            ),
        }

    def stop_hotspot(self, confirm: bool = False) -> Dict:
        """Stop broadcasting the hotspot (configuration is kept, so it
        can be restarted with start_hotspot). Confirm-gated."""
        if not confirm:
            return {
                "success": False,
                "needs_confirmation": True,
                "preview": "Would stop the mobile hotspot - connected devices will be dropped.",
                "message": "Call again with confirm=true to stop.",
            }
        result = self._run(["wlan", "stop", "hostednetwork"])
        if "error" in result:
            return result
        return {
            "success": result["success"],
            "stopped": result["success"],
            "error": None if result["success"] else (result["stderr"] or result["stdout"]),
        }

    def get_connected_devices(self) -> Dict:
        """List devices currently connected to the hotspot (parsed from
        the hosted-network status output)."""
        status = self.get_hotspot_status()
        if "error" in status:
            return status
        raw = status.get("raw", "")
        count_match = re.search(r"Number of client.*?:\s*(\d+)", raw, re.IGNORECASE)
        macs = re.findall(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", raw)
        return {
            "success": True,
            "connected_count": int(count_match.group(1)) if count_match else len(macs),
            "client_macs": macs,
        }
