"""Power management
================
Power *plan* and sleep-state management - distinct from
windows/system_info/power.py's shutdown/restart/sign-out/lock, which
this module leaves alone. Covers: sleep/hibernate now, listing and
switching power plans (via `powercfg`), battery saver, and querying/
setting the screen & sleep timeouts of the active plan.
"""

import ctypes
import re
import subprocess
from typing import Dict

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class PowerManager:
    """Sleep/hibernate, power plans, and timeout settings."""

    def sleep_now(self) -> Dict:
        """Put the PC to sleep immediately."""
        try:
            ctypes.windll.powrprof.SetSuspendState(False, True, False)  # sleep, not hibernate, no forced apps-close
            return {"success": True, "message": "Sleeping"}
        except Exception as e:
            return {"error": str(e)}

    def hibernate_now(self) -> Dict:
        """Hibernate the PC immediately."""
        try:
            ctypes.windll.powrprof.SetSuspendState(True, True, False)
            return {"success": True, "message": "Hibernating"}
        except Exception as e:
            return {"error": str(e)}

    def get_battery_status(self) -> Dict:
        """Battery percent, charging state, and time remaining."""
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        battery = psutil.sensors_battery()
        if battery is None:
            return {"has_battery": False}
        secs_left = battery.secsleft
        return {
            "has_battery": True,
            "percent": battery.percent,
            "plugged_in": battery.power_plugged,
            "minutes_remaining": (
                None
                if secs_left in (None, psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN)
                else round(secs_left / 60)
            ),
        }

    def list_power_plans(self) -> Dict:
        """List available Windows power plans (powercfg /list)."""
        try:
            result = subprocess.run(["powercfg", "/list"], capture_output=True, text=True, check=True, timeout=10)
            plans = []
            for line in result.stdout.splitlines():
                m = re.search(r"Power Scheme GUID:\s*([0-9a-fA-F-]+)\s*\((.+?)\)\s*(\*)?", line)
                if m:
                    plans.append({"guid": m.group(1), "name": m.group(2), "active": bool(m.group(3))})
            return {"plans": plans, "count": len(plans)}
        except Exception as e:
            return {"error": str(e)}

    def get_active_power_plan(self) -> Dict:
        listing = self.list_power_plans()
        if "error" in listing:
            return listing
        active = next((p for p in listing["plans"] if p["active"]), None)
        return {"active_plan": active} if active else {"error": "Could not determine active plan"}

    def set_power_plan(self, plan_name: str) -> Dict:
        """Switch the active power plan by (partial, case-insensitive) name,
        e.g. 'balanced', 'high performance', 'power saver'."""
        listing = self.list_power_plans()
        if "error" in listing:
            return listing
        match = next((p for p in listing["plans"] if plan_name.lower() in p["name"].lower()), None)
        if not match:
            return {
                "error": f"No power plan matching '{plan_name}'",
                "available": [p["name"] for p in listing["plans"]],
            }
        try:
            subprocess.run(["powercfg", "/setactive", match["guid"]], check=True, timeout=10)
            return {"success": True, "activated": match["name"]}
        except Exception as e:
            return {"error": str(e)}

    def set_sleep_timeout(self, minutes: int, on_battery: bool = False) -> Dict:
        """Set how many minutes of inactivity before the PC sleeps. 0 = never."""
        try:
            flag = "/setdcvalueindex" if on_battery else "/setacvalueindex"
            subprocess.run(
                ["powercfg", flag, "scheme_current", "sub_sleep", "standbyidle", str(minutes)], check=True, timeout=10
            )
            subprocess.run(["powercfg", "/setactive", "scheme_current"], check=True, timeout=10)
            return {"success": True, "sleep_timeout_minutes": minutes, "on_battery": on_battery}
        except Exception as e:
            return {"error": str(e)}

    def set_screen_timeout(self, minutes: int, on_battery: bool = False) -> Dict:
        """Set how many minutes of inactivity before the screen turns off. 0 = never."""
        try:
            flag = "/setdcvalueindex" if on_battery else "/setacvalueindex"
            subprocess.run(
                ["powercfg", flag, "scheme_current", "sub_video", "videoidle", str(minutes)], check=True, timeout=10
            )
            subprocess.run(["powercfg", "/setactive", "scheme_current"], check=True, timeout=10)
            return {"success": True, "screen_timeout_minutes": minutes, "on_battery": on_battery}
        except Exception as e:
            return {"error": str(e)}

    def enable_battery_saver(self) -> Dict:
        """Switch to the Power Saver plan as a simple stand-in for battery saver mode."""
        return self.set_power_plan("power saver")

    def disable_battery_saver(self) -> Dict:
        """Switch back to the Balanced plan."""
        return self.set_power_plan("balanced")
