"""
HOME (Phase 18.9)
=====================
Local control for the physical fixtures of the house:

    light_control.py    - on/off/brightness/color for smart bulbs
                          (`phue` against a real Hue bridge if
                          configured, else a simulated registry).
    ac_control.py       - power/mode/target-temperature for one or
                          more climate units (`requests` against a
                          configured host, else simulated).
    door_control.py     - lock/unlock for smart locks, gated behind
                          security's intruder_alert.py so
                          repeated bad door codes count toward the
                          same alert threshold as bad faces/voices.
    camera_guard.py     - motion-triggered snapshots (`cv2`),
                          privacy-aware via SECURITY's
                          privacy_shield.py and alert-aware via
                          SECURITY's intruder_alert.py.
    routine.py          - named scenes (leaving_home, arriving_home,
                          movie_night) that fan out across the four
                          modules above, plus run_custom() for
                          anything not shipped built in.

Every optional third-party dependency (`phue`, `requests`, `cv2`) is
import-guarded; missing any of them degrades that module to its
simulated fallback rather than breaking the package. All local state
(light/climate/door registries, armed-camera flags, snapshots) lives
under data/smart_devices/ by default, each path overridable via its
own SMART_DEVICES_*_ENV variable.

Purely additive - nothing in Phase 1-18.8 imports from here. The two
imports this package does make (privacy_shield.py, intruder_alert.py
from security) are themselves import-guarded, so this
package still works standalone if 18.8 isn't present.
"""

from home.light_control import get_light_control
from home.ac_control import get_ac_control
from home.door_control import get_door_control
from home.camera_guard import get_camera_guard
from home.routine import get_routine

__all__ = [
    "get_light_control",
    "get_ac_control",
    "get_door_control",
    "get_camera_guard",
    "get_routine",
]
