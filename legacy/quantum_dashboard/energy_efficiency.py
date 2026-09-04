"""
energy_efficiency.py
======================
Battery/power status plus a "what's likely draining the battery"
list, built from per-process CPU share (a reasonable proxy for power
draw on a laptop without vendor-specific power APIs). Gives simple,
actionable suggestions.

Dependencies: pip install psutil screen-brightness-control
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import psutil

try:
    import screen_brightness_control as sbc
except ImportError:  # pragma: no cover
    sbc = None

logger = logging.getLogger("ultron.energy_efficiency")


@dataclass
class PowerStatus:
    on_battery: bool
    battery_percent: Optional[float]
    minutes_remaining: Optional[int]
    brightness_percent: Optional[int]


@dataclass
class ProcessDraw:
    pid: int
    name: str
    cpu_percent: float


class EnergyEfficiency:
    def power_status(self) -> PowerStatus:
        batt = psutil.sensors_battery()
        brightness = None
        if sbc is not None:
            try:
                brightness = sbc.get_brightness(display=0)[0]
            except Exception:
                brightness = None

        if batt is None:
            return PowerStatus(
                on_battery=False, battery_percent=None, minutes_remaining=None, brightness_percent=brightness
            )

        return PowerStatus(
            on_battery=not batt.power_plugged,
            battery_percent=batt.percent,
            minutes_remaining=None if batt.secsleft in (-1, -2) else batt.secsleft // 60,
            brightness_percent=brightness,
        )

    def top_power_consumers(self, top_n: int = 5, sample_seconds: float = 1.0) -> List[ProcessDraw]:
        """CPU share as a proxy for power draw. Not exact wattage, but
        useful for 'what's likely eating my battery right now'."""
        import time

        procs = list(psutil.process_iter(["pid", "name"]))
        for p in procs:
            try:
                p.cpu_percent(interval=None)  # prime the counter
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                from core.error_trace import log_swallowed as _lsw

                _lsw("quantum_dashboard.energy_efficiency.top_power_consumers")
        time.sleep(sample_seconds)

        results = []
        for p in procs:
            try:
                cpu = p.cpu_percent(interval=None)
                if cpu > 0:
                    results.append(ProcessDraw(pid=p.pid, name=p.info.get("name") or "unknown", cpu_percent=cpu))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        results.sort(key=lambda x: x.cpu_percent, reverse=True)
        return results[:top_n]

    def suggestions(self) -> List[str]:
        status = self.power_status()
        tips = []
        if status.on_battery and status.battery_percent is not None and status.battery_percent < 20:
            tips.append("Battery below 20% - consider plugging in.")
        if status.brightness_percent and status.brightness_percent > 70 and status.on_battery:
            tips.append(
                f"Screen brightness is {status.brightness_percent}% on battery - "
                "dimming to ~50% noticeably extends runtime."
            )
        top = self.top_power_consumers(top_n=3)
        if top and top[0].cpu_percent > 40:
            tips.append(
                f"'{top[0].name}' is using {top[0].cpu_percent:.0f}% CPU - "
                "likely the biggest battery drain right now."
            )
        return tips


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ee = EnergyEfficiency()
    print(ee.power_status())
    print(ee.top_power_consumers())
    print(ee.suggestions())
