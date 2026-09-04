"""
Routine (HOME)
==================
Named scenes that fan a single call out across this package's other
four modules - light_control.py, ac_control.py, door_control.py and
camera_guard.py - rather than a caller having to know which knobs
"leaving home" or "movie night" actually touches. Three routines ship
built in (LEAVING_HOME, ARRIVING_HOME, MOVIE_NIGHT); run_custom()
covers anything else without needing a new function per scene.

Each step is best-effort and independent: one module raising or
returning success: False doesn't stop the rest from running, since a
light that fails to turn off shouldn't leave the door unlocked. Every
step's own result is collected so a caller can see exactly what
happened, not just a single pass/fail for the whole routine. Nothing
here is scheduled automatically - a wake-word phrase, a cron job, or
a geofence trigger higher up is expected to call run().
"""

from typing import Callable, Dict, List, Optional

from home.light_control import get_light_control
from home.ac_control import get_ac_control
from home.door_control import get_door_control
from home.camera_guard import get_camera_guard

LEAVING_HOME = "leaving_home"
ARRIVING_HOME = "arriving_home"
MOVIE_NIGHT = "movie_night"


class Routine:
    """Named multi-module HOME scenes. Use get_routine()."""

    def _run_steps(self, steps: List[Callable[[], Dict]]) -> Dict:
        results = []
        for step in steps:
            try:
                results.append(step())
            except Exception as exc:
                results.append({"success": False, "error": str(exc)})
        return {"success": all(r.get("success", False) for r in results), "steps": results}

    def run(self, name: str, *, light_ids: Optional[List[str]] = None, ac_unit_ids: Optional[List[str]] = None) -> Dict:
        """Runs the built-in routine `name` (LEAVING_HOME,
        ARRIVING_HOME or MOVIE_NIGHT). `light_ids`/`ac_unit_ids` scope
        which devices are touched - omit either to skip that device
        type for this run rather than guessing at every light/unit
        this build has ever seen. Returns {"success": bool, "steps":
        List[dict], "error": Optional[str]}, where "success" is True
        only if every individual step succeeded."""
        light_ids = light_ids or []
        ac_unit_ids = ac_unit_ids or []

        if name == LEAVING_HOME:
            steps = [lambda: get_light_control().turn_off(lid) for lid in light_ids]
            steps += [lambda: get_ac_control().turn_off(uid) for uid in ac_unit_ids]
            steps.append(lambda: get_door_control().lock_all())
            steps.append(
                lambda: {
                    "success": True,
                    "error": None,
                    "cameras_armed": [
                        cid for cid in get_camera_guard().list_cameras() if get_camera_guard().arm(cid)["success"]
                    ],
                }
            )
        elif name == ARRIVING_HOME:
            steps = [lambda: get_light_control().turn_on(lid, brightness=80) for lid in light_ids]
            steps += [lambda: get_ac_control().turn_on(uid, mode="auto") for uid in ac_unit_ids]
        elif name == MOVIE_NIGHT:
            steps = [lambda: get_light_control().set_brightness(lid, 15) for lid in light_ids]
            steps += [lambda: get_ac_control().turn_on(uid, mode="cool") for uid in ac_unit_ids]
        else:
            return {"success": False, "steps": [], "error": f"unknown routine '{name}'"}

        result = self._run_steps(steps)
        result["error"] = None
        return result

    def run_custom(self, steps: List[Callable[[], Dict]]) -> Dict:
        """Runs an arbitrary ordered list of zero-arg callables (each
        expected to return a dict with a "success" key, matching
        every other HOME module's convention), for scenes this module
        doesn't ship built in. Returns the same shape as run()."""
        result = self._run_steps(steps)
        result["error"] = None
        return result


_routine: Optional[Routine] = None


def get_routine() -> Routine:
    global _routine
    if _routine is None:
        _routine = Routine()
    return _routine
