"""
driver_controller.py
=====================
High-level hardware control: screen brightness, system volume,
battery/power status. This talks to existing Windows APIs/WMI, not to
raw device drivers - "driver" here means "the thing that drives your
screen/speakers", not kernel driver installation.

Dependencies: pip install screen-brightness-control pycaw comtypes wmi
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("ultron.driver_controller")

try:
    import screen_brightness_control as sbc
except ImportError:  # pragma: no cover
    sbc = None

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    _AUDIO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AUDIO_AVAILABLE = False

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


@dataclass
class BatteryStatus:
    percent: float
    plugged_in: bool
    minutes_remaining: Optional[int]


class DriverController:
    """Unified control surface for brightness / volume / power."""

    # ------------------------------------------------------- brightness
    def get_brightness(self) -> Optional[int]:
        if sbc is None:
            logger.error("screen_brightness_control not installed")
            return None
        try:
            return sbc.get_brightness(display=0)[0]
        except Exception as e:
            logger.error("get_brightness failed: %s", e)
            return None

    def set_brightness(self, percent: int) -> bool:
        if sbc is None:
            logger.error("screen_brightness_control not installed")
            return False
        percent = max(0, min(100, percent))
        try:
            sbc.set_brightness(percent)
            logger.info("Brightness set to %d%%", percent)
            return True
        except Exception as e:
            logger.error("set_brightness failed: %s", e)
            return False

    # ------------------------------------------------------------ volume
    def _volume_interface(self):
        speakers = AudioUtilities.GetSpeakers()
        interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    def get_volume(self) -> Optional[int]:
        if not _AUDIO_AVAILABLE:
            logger.error("pycaw/comtypes not installed")
            return None
        vol = self._volume_interface()
        scalar = vol.GetMasterVolumeLevelScalar()
        return round(scalar * 100)

    def set_volume(self, percent: int) -> bool:
        if not _AUDIO_AVAILABLE:
            logger.error("pycaw/comtypes not installed")
            return False
        percent = max(0, min(100, percent))
        vol = self._volume_interface()
        vol.SetMasterVolumeLevelScalar(percent / 100, None)
        logger.info("Volume set to %d%%", percent)
        return True

    def mute(self, muted: bool = True) -> bool:
        if not _AUDIO_AVAILABLE:
            return False
        vol = self._volume_interface()
        vol.SetMute(1 if muted else 0, None)
        return True

    # -------------------------------------------------------------- power
    def battery_status(self) -> Optional[BatteryStatus]:
        if psutil is None:
            return None
        batt = psutil.sensors_battery()
        if batt is None:
            return None  # desktop with no battery
        return BatteryStatus(
            percent=batt.percent,
            plugged_in=batt.power_plugged,
            minutes_remaining=None if batt.secsleft in (-1, -2) else batt.secsleft // 60,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    dc = DriverController()
    print("Brightness:", dc.get_brightness())
    print("Volume:", dc.get_volume())
    print("Battery:", dc.battery_status())
