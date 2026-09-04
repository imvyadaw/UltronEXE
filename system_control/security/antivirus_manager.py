"""Antivirus Manager
=====================
Queries the Windows Security Center (WMI root\\SecurityCenter2) for
ALL antivirus products registered with Windows - not just Defender.
Distinct from defender_manager.py, which controls Defender's own
settings/scans/exclusions specifically - this module answers "what
AV is installed and is it healthy", whether that's Defender, a
third-party product, or both, and can nudge Windows Security Center
to re-check state. It does not attempt to drive third-party vendor
UIs (no stable, vendor-agnostic CLI exists for that), so control
methods here are limited to opening the relevant Windows Security
app pages.

Status reads need no admin. Nothing here changes protection state
directly (that's defender_manager's job for Defender, or the vendor's
own app for third-party products), so nothing is confirm-gated.
"""

import subprocess
from typing import Dict


class AntivirusManager:
    """Inspect all antivirus products registered with Windows Security Center."""

    def _run_ps(self, script: str, timeout: float = 30.0) -> Dict:
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

    _STATE_BITS = {
        # productState is a bitmask; middle byte's low nibble = on/off, high nibble = up to date
        "enabled": lambda s: bool((s >> 12) & 0x1) if isinstance(s, int) else None,
    }

    def _decode_product_state(self, product_state) -> Dict:
        try:
            s = int(product_state)
        except (TypeError, ValueError):
            return {"enabled": None, "up_to_date": None}
        hex_state = f"{s:06x}"
        enabled = hex_state[2:4] in ("10", "11")
        up_to_date = hex_state[4:6] == "00"
        return {"enabled": enabled, "up_to_date": up_to_date}

    def list_registered_products(self) -> Dict:
        """List every antivirus product Windows Security Center knows about,
        with enabled/up-to-date state decoded from productState."""
        script = (
            "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | "
            "Select-Object displayName, productState, pathToSignedProductExe | ConvertTo-Json"
        )
        result = self._run_ps(script)
        if "error" in result:
            return result
        if not result["success"]:
            return {
                "error": result["stderr"]
                or "Could not query Security Center - it may not be running (common on Server SKUs)."
            }
        import json

        try:
            data = json.loads(result["stdout"]) if result["stdout"] else []
            if isinstance(data, dict):
                data = [data]
        except Exception:
            return {"error": "Could not parse Security Center response.", "raw": result["stdout"]}
        products = []
        for p in data:
            decoded = self._decode_product_state(p.get("productState"))
            products.append(
                {
                    "name": p.get("displayName"),
                    "enabled": decoded["enabled"],
                    "up_to_date": decoded["up_to_date"],
                    "path": p.get("pathToSignedProductExe"),
                }
            )
        return {"products": products, "count": len(products)}

    def get_active_antivirus(self) -> Dict:
        """Return whichever registered AV product(s) are currently enabled -
        the machine's actual real-time protection, whoever provides it."""
        listed = self.list_registered_products()
        if "error" in listed:
            return listed
        active = [p for p in listed["products"] if p["enabled"]]
        if not active:
            return {"protected": False, "message": "No enabled antivirus product found in Security Center."}
        return {"protected": True, "active_products": active}

    def is_any_av_outdated(self) -> Dict:
        """Flag any enabled AV product whose signatures Security Center considers stale."""
        listed = self.list_registered_products()
        if "error" in listed:
            return listed
        outdated = [p for p in listed["products"] if p["enabled"] and p["up_to_date"] is False]
        return {"outdated_products": outdated, "any_outdated": len(outdated) > 0}

    def open_security_app(self, page: str = "home") -> Dict:
        """Open the Windows Security app to a given page (home, virus, app-browser,
        account, device, network, family). No headless CLI exists to drive
        third-party AV UIs, so this opens the relevant OS surface instead."""
        pages = {
            "home": "windowsdefender:",
            "virus": "windowsdefender://threat",
            "app-browser": "windowsdefender://appbrowser",
            "account": "windowsdefender://account",
            "device": "windowsdefender://device",
            "network": "windowsdefender://network",
            "family": "windowsdefender://family",
        }
        uri = pages.get(page, pages["home"])
        try:
            subprocess.Popen(["start", uri], shell=True)
            return {"success": True, "opened": page}
        except Exception as e:
            return {"error": str(e)}
