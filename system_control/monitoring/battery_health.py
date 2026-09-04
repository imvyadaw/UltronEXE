"""Battery Health Monitor
=========================
Battery wear/degradation via Windows' own `powercfg /batteryreport`
(design capacity vs current full-charge capacity) plus a live charge/
status snapshot via WMI - there is no other first-party source for
long-term battery wear on Windows. Desktops and other AC-only systems
report this plainly as unavailable rather than raising.

All reads; nothing here changes system state, so nothing is
confirm-gated.
"""
import logging

import subprocess
import tempfile
import os
import re
from typing import Dict


class BatteryHealthMonitor:
    """Battery wear (design vs full-charge capacity), live charge
    status, and cycle-count estimate, sourced from powercfg's own
    battery report - no third-party tools needed."""

    def _run_ps(self, cmd: str, timeout: float = 20.0) -> Dict:
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {"success": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
        except FileNotFoundError:
            return {"error": "PowerShell not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except Exception as e:
            return {"error": str(e)}

    def get_current_status(self) -> Dict:
        """Live charge percentage, charging/discharging state, and
        estimated runtime via WMI. Returns available=False on desktops
        or any system with no battery, rather than an error - that's
        an expected, common case, not a failure."""
        result = self._run_ps(
            "Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | "
            "Select-Object EstimatedChargeRemaining, BatteryStatus, EstimatedRunTime | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"] or not result["stdout"]:
            return {"success": True, "available": False, "reason": "No battery detected (desktop or AC-only system)."}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse battery status"}
        if isinstance(data, list):
            data = data[0] if data else {}
        status_map = {
            1: "discharging",
            2: "on AC, not charging",
            3: "fully charged",
            4: "low",
            5: "critical",
            6: "charging",
            7: "charging (high)",
            8: "charging (low)",
            9: "charging (critical)",
            10: "undefined",
            11: "partially charged",
        }
        runtime = data.get("EstimatedRunTime")
        return {
            "success": True,
            "available": True,
            "charge_percent": data.get("EstimatedChargeRemaining"),
            "status": status_map.get(data.get("BatteryStatus"), "unknown"),
            "estimated_runtime_minutes": None if runtime in (None, 71582788) else runtime,
        }

    def generate_wear_report(self) -> Dict:
        """Run `powercfg /batteryreport`, parse the generated HTML for
        design capacity vs full-charge capacity, and compute wear as a
        percentage of original capacity lost. This is the only
        first-party source for battery degradation on Windows - no
        admin needed, but not available on desktops."""
        tmp_dir = tempfile.gettempdir()
        report_path = os.path.join(tmp_dir, "ultron_battery_report.html")
        try:
            result = subprocess.run(
                ["powercfg", "/batteryreport", "/output", report_path, "/duration", "7"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return {"error": "powercfg not found - this is only available on Windows"}
        except subprocess.TimeoutExpired:
            return {"error": "powercfg timed out generating the report"}
        except Exception as e:
            return {"error": str(e)}

        if result.returncode != 0 or not os.path.exists(report_path):
            stderr = (result.stderr or result.stdout or "").strip()
            if "no battery" in stderr.lower() or not stderr:
                return {
                    "success": True,
                    "available": False,
                    "reason": "No battery detected (desktop or AC-only system).",
                }
            return {"error": stderr or "powercfg /batteryreport failed"}

        try:
            with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()
        except Exception as e:
            return {"error": f"Could not read generated report: {e}"}
        finally:
            try:
                os.remove(report_path)
            except OSError:
                logging.getLogger(__name__).exception("Suppressed OSError")

        def _mwh(pattern: str):
            m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if not m:
                return None
            digits = re.sub(r"[^\d]", "", m.group(1))
            return int(digits) if digits else None

        design_capacity = _mwh(r"DESIGN CAPACITY</span>\s*</td>\s*<td[^>]*>\s*<span[^>]*>([\d,]+)\s*mWh")
        full_charge = _mwh(r"FULL CHARGE CAPACITY</span>\s*</td>\s*<td[^>]*>\s*<span[^>]*>([\d,]+)\s*mWh")

        if not design_capacity or not full_charge:
            return {
                "success": True,
                "available": True,
                "parsed": False,
                "note": "Report generated but capacity fields could not be parsed from this Windows build's report layout.",
            }

        wear_percent = round((1 - (full_charge / design_capacity)) * 100, 1)
        return {
            "success": True,
            "available": True,
            "parsed": True,
            "design_capacity_mwh": design_capacity,
            "full_charge_capacity_mwh": full_charge,
            "wear_percent": max(0.0, wear_percent),
            "health_percent": round(100 - max(0.0, wear_percent), 1),
        }
