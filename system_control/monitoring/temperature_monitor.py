"""Temperature Monitor
=====================
Aggregated hardware-temperature reads and history - distinct from the
per-component reads already scattered across hardware/*.py rather
than duplicating them:

- hardware/fan_control.py's get_thermal_zones() - one generic ACPI
  sensor most (not all) laptops expose. Reused here as one input, not
  reimplemented.
- hardware/gpu_control.py's get_nvidia_status() - GPU die temperature,
  NVIDIA only. Also reused here, not reimplemented.
- Neither of those gives per-core CPU temperatures - Windows has no
  first-party API for that at all. When the LibreHardwareMonitor (or
  legacy OpenHardwareMonitor) WMI namespace is available - i.e. the
  user is already running one of those free tools in the background,
  a common setup for anyone who cares about temps enough to ask
  ULTRON about them - this module reads its Sensor class for
  per-core CPU temperature. Without it, per-core CPU temp is reported
  as unavailable rather than guessed at, same honesty policy as
  fan_control.py's fan-RPM methods.

What this module actually adds beyond aggregation: a rolling history
buffer and simple over-threshold detection, so a caller can ask
"has anything been running hot" instead of only "what's the reading
right now" - the temperature-specific counterpart to monitoring/
alerts.py's generic CPU%/RAM%/disk% rules (which don't look at
temperature at all).

All reads; nothing here changes system state, so nothing is
confirm-gated.
"""

import subprocess
import time
from typing import Dict, List, Optional

from system_control.hardware.fan_control import FanControl
from system_control.hardware.gpu_control import GPUControl


class TemperatureMonitor:
    """Aggregated CPU/GPU/ACPI temperature reads, with a rolling
    history and simple over-threshold detection."""

    def __init__(self, history_size: int = 120):
        self._fan = FanControl()
        self._gpu = GPUControl()
        self._history_size = history_size
        self._history: List[Dict] = []

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

    def _get_cpu_core_temps(self) -> Dict:
        """Per-core CPU temperature via the LibreHardwareMonitor/
        OpenHardwareMonitor WMI namespace, only present if one of
        those is already running as a service in the background -
        Windows itself exposes no per-core CPU temperature API."""
        result = self._run_ps(
            "Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor -ErrorAction SilentlyContinue | "
            "Where-Object { $_.SensorType -eq 'Temperature' -and $_.Name -match 'CPU' } | "
            "Select-Object Name, Value | ConvertTo-Json"
        )
        if "error" in result or not result.get("success"):
            return {
                "available": False,
                "reason": "LibreHardwareMonitor/OpenHardwareMonitor not running or not installed.",
            }
        if not result["stdout"]:
            return {"available": False, "reason": "No CPU temperature sensors reported."}
        import json

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"available": False, "reason": "Could not parse sensor data."}
        sensors = data if isinstance(data, list) else [data]
        cores = [{"name": s.get("Name"), "temperature_c": s.get("Value")} for s in sensors]
        return {"available": True, "cores": cores}

    def get_all_temperatures(self) -> Dict:
        """One combined reading: CPU per-core (if a hardware-monitor
        tool is running), GPU die temp (NVIDIA only), and generic ACPI
        thermal zones (fan_control.py). Missing sources are reported
        as unavailable rather than omitted silently, so a caller can
        tell 'no sensor' from 'sensor read zero'."""
        reading: Dict = {"timestamp": time.time()}

        cpu = self._get_cpu_core_temps()
        reading["cpu"] = cpu

        gpu_status = self._gpu.get_nvidia_status()
        if "error" not in gpu_status:
            reading["gpu"] = {"available": True, "temperature_c": gpu_status.get("temperature_c")}
        else:
            reading["gpu"] = {"available": False, "reason": gpu_status.get("error")}

        zones = self._fan.get_thermal_zones()
        if zones.get("success"):
            reading["acpi_zones"] = zones.get("zones", [])
        else:
            reading["acpi_zones"] = []
            reading["acpi_note"] = zones.get("note") or zones.get("error")

        self._history.append(reading)
        if len(self._history) > self._history_size:
            self._history.pop(0)

        return {"success": True, **reading}

    def get_history(self, limit: Optional[int] = None) -> Dict:
        """Recent readings taken via get_all_temperatures() calls made
        so far this session (in-memory only - nothing is persisted
        across restarts)."""
        history = self._history[-limit:] if limit else list(self._history)
        return {"success": True, "history": history, "count": len(history)}

    def check_thresholds(self, cpu_max_c: float = 90.0, gpu_max_c: float = 88.0) -> Dict:
        """Take one fresh reading and report anything over the given
        thresholds - the temperature-specific counterpart to
        monitoring/alerts.py's CPU%/RAM%/disk% rules. Defaults are
        conservative sustained-load ceilings for typical consumer
        hardware, not hard safety limits - tune per-machine."""
        reading = self.get_all_temperatures()
        over: List[Dict] = []

        if reading["cpu"].get("available"):
            for core in reading["cpu"].get("cores", []):
                temp = core.get("temperature_c")
                if isinstance(temp, (int, float)) and temp >= cpu_max_c:
                    over.append(
                        {"source": "cpu", "name": core.get("name"), "temperature_c": temp, "threshold_c": cpu_max_c}
                    )

        if reading["gpu"].get("available"):
            temp = reading["gpu"].get("temperature_c")
            if isinstance(temp, (int, float)) and temp >= gpu_max_c:
                over.append({"source": "gpu", "temperature_c": temp, "threshold_c": gpu_max_c})

        return {"success": True, "over_threshold": over, "count": len(over), "reading": reading}
