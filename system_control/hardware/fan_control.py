"""Fan Control
=============
Thermal reads and the one fan-related setting Windows actually exposes
a supported API for: "System cooling policy" (Active vs Passive - does
Windows ramp the fan up first or throttle the CPU first when hot).

There is deliberately no direct fan-RPM/duty-cycle control here.
Windows has no first-party, vendor-neutral API for that - real fan-
curve control goes through the embedded controller via a
manufacturer's own proprietary interface (Dell/Lenovo/ASUS/etc, each
different and mostly undocumented), the same reason tools like
NoteBook FanControl and HWiNFO need a matching per-vendor plugin
rather than one universal driver. set_fan_speed/get_fan_rpm below
report that plainly (not a guess, not a partial fake reading) so
callers don't mistake "unsupported" for "0 RPM" or silently do
nothing. get_thermal_zones reads the generic ACPI thermal zone
temperature that most (not all) laptops expose - useful signal even
without fan control.

set_cooling_policy is confirm-gated and needs admin: Active
(fan-first) trades battery/noise for lower CPU temps and less
throttling; Passive (throttle-first) is quieter/cooler-running but
can noticeably reduce sustained performance.
"""

import subprocess
from typing import Dict

# powercfg GUIDs for the "Processor power management > System cooling
# policy" setting - stable across Windows versions.
_SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
_SYSCOOLINGPOLICY = "94d3a615-a899-4ac5-ae2b-e4d8f634367f"
_POLICY_VALUES = {"active": 1, "passive": 0}


class FanControl:
    """Thermal zone reads and system cooling policy (active vs
    passive). Does not and cannot expose direct fan RPM/duty-cycle
    control - see module docstring."""

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

    def get_thermal_zones(self) -> Dict:
        """Generic ACPI thermal-zone temperatures (root\\WMI
        MSAcpi_ThermalZoneTemperature), where the firmware exposes
        them - many desktops and some laptops don't publish this at
        all, in which case an empty list is returned (not an error).
        No admin needed."""
        result = self._run_ps(
            "Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature "
            "-ErrorAction SilentlyContinue | Select-Object InstanceName, CurrentTemperature | ConvertTo-Json"
        )
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "Could not query thermal zones"}
        if not result["stdout"]:
            return {
                "success": True,
                "zones": [],
                "count": 0,
                "note": "No ACPI thermal zones exposed by this system's firmware.",
            }
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"error": "Could not parse thermal zone data"}
        zones = data if isinstance(data, list) else [data]
        for z in zones:
            raw = z.get("CurrentTemperature")
            if raw is not None:
                # MSAcpi reports tenths of a Kelvin.
                z["temperature_c"] = round(raw / 10.0 - 273.15, 1)
        return {"success": True, "zones": zones, "count": len(zones)}

    def get_cooling_policy(self) -> Dict:
        """Current 'System cooling policy' for the active power scheme
        (AC): 'active' (fan ramps up before throttling) or 'passive'
        (throttles before ramping the fan). No admin needed."""
        result = self._run_ps(f"powercfg /getactvalueindex SCHEME_CURRENT {_SUB_PROCESSOR} {_SYSCOOLINGPOLICY}")
        if "error" in result:
            return result
        if not result["success"]:
            return {"error": result["stderr"] or "powercfg query failed"}
        digits = "".join(c for c in result["stdout"] if c.isdigit())
        if not digits:
            return {"error": "Could not parse cooling policy", "raw": result["stdout"]}
        value = int(digits)
        name = next((k for k, v in _POLICY_VALUES.items() if v == value), f"unknown ({value})")
        return {"success": True, "policy": name}

    def set_cooling_policy(self, policy: str, on_battery: bool = False, confirm: bool = False) -> Dict:
        """Set 'System cooling policy' to 'active' (fan-first: cooler,
        louder, more battery use) or 'passive' (throttle-first:
        quieter, can reduce sustained performance). Confirm-gated,
        needs admin."""
        value = _POLICY_VALUES.get(policy.lower())
        if value is None:
            return {"error": f"Unknown policy '{policy}'. Use one of: {sorted(_POLICY_VALUES)}"}
        scope = "battery (DC)" if on_battery else "plugged in (AC)"
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will set the system cooling policy to '{policy}' while {scope}. Needs Administrator.",
            }
        flag = "/setdcvalueindex" if on_battery else "/setacvalueindex"
        result = self._run_ps(
            f"powercfg {flag} SCHEME_CURRENT {_SUB_PROCESSOR} {_SYSCOOLINGPOLICY} {value}; "
            f"powercfg /setactive SCHEME_CURRENT"
        )
        if "error" in result:
            return result
        if not result["success"]:
            err = result["stderr"] or "Failed to set cooling policy"
            if "access" in err.lower() or "denied" in err.lower():
                err += " - run ULTRON as Administrator."
            return {"error": err}
        return {"success": True, "policy": policy, "on_battery": on_battery}

    def get_fan_rpm(self) -> Dict:
        """Always unsupported - see module docstring. Present so
        callers get a clear, explicit answer instead of guessing this
        method doesn't exist."""
        return {
            "error": "Direct fan RPM reading isn't exposed by any vendor-neutral Windows API. "
            "It requires a manufacturer-specific embedded-controller interface "
            "(e.g. a Dell/Lenovo/ASUS SDK) that this module doesn't have a backend for. "
            "get_thermal_zones() is the closest supported signal this module can offer."
        }

    def set_fan_speed(self, percent: int, confirm: bool = False) -> Dict:
        """Always unsupported - see module docstring."""
        return {
            "error": "Direct fan speed/duty-cycle control isn't exposed by any vendor-neutral Windows API. "
            "It requires a manufacturer-specific embedded-controller interface that this module "
            "doesn't have a backend for. set_cooling_policy() is the closest supported control "
            "this module can offer (active vs passive cooling behavior)."
        }
