"""
DEVICES (Phase 18.9)
=========================
Local control for personal devices linked to the project, as opposed
to HOME/'s fixed household fixtures:

    phone_link.py   - pairing + notification forwarding for a phone
                      (push via a configured gateway, else queued
                      locally).
    watch_link.py   - pairing + health-metric ingestion (steps, heart
                      rate, battery) for a smartwatch, plus
                      notification forwarding reusing phone_link's
                      push gateway.
    tv_control.py   - power/volume/input/app-launch for a smart TV
                      over Roku's External Control Protocol, else
                      simulated.
    car_link.py     - lock/unlock and location lookup for a car,
                      mirroring HOME/door_control.py's code-gated
                      shape and reporting into
                      PHASE_18_8_SECURITY's intruder_alert.py the
                      same way.
    sync_all.py     - one status snapshot across all four modules,
                      plus notify_all() to broadcast a message to
                      every paired phone and watch at once.

Every optional third-party dependency (`requests`) is import-guarded;
without it, or without a device's host/gateway configured, every
module falls back to its own simulated registry rather than raising.
All local state lives under data/smart_devices/ by default, each path
overridable via its own SMART_DEVICES_*_ENV variable - none of it is
ever uploaded anywhere by this package.

Purely additive - nothing in Phase 1-18.8 imports from here. This
package's own import from PHASE_18_8_SECURITY (car_link.py's
intruder_alert.py hook) is itself import-guarded, so DEVICES/ still
works standalone if 18.8 isn't present.
"""

from devices.phone_link import get_phone_link
from devices.watch_link import get_watch_link
from devices.tv_control import get_tv_control
from devices.car_link import get_car_link
from devices.sync_all import get_sync_all

__all__ = [
    "get_phone_link",
    "get_watch_link",
    "get_tv_control",
    "get_car_link",
    "get_sync_all",
]
