"""
Mission Manager (P1 - Mission Persistence Engine)
==================================================
Entry point for the mission_engine/ package. Ties mission_store.py's
sqlite persistence to a simple lifecycle API and, critically, to
startup auto-resume: on process start something calls
get_resumable_mission() to find "what was I in the middle of" from a
previous run and hands that context back to the model instead of the
user having to re-explain themselves after a restart/crash.

Usage:
    from intelligence.mission_engine import get_mission_manager
    mm = get_mission_manager()
    mission = mm.create_mission("Plan the Bangalore trip")
    mm.checkpoint(mission["id"], "Picked dates: Nov 12-16, booked flights")
    ...later, after a restart...
    resumable = mm.get_resumable_mission()
    if resumable:
        mm.resume_mission(resumable["id"])

Idle threshold: a mission is only offered for auto-resume if it was
last touched more than IDLE_RESUME_SECONDS ago (default 5 min) - a
mission still being actively worked on in the current session
shouldn't interrupt with "welcome back" prompts about itself.
"""

import time
from typing import Dict, List, Optional

from intelligence.mission_engine.mission_store import get_mission_store

IDLE_RESUME_SECONDS = 5 * 60


class MissionManager:
    def __init__(self):
        self._store = get_mission_store()

    # -- lifecycle --------------------------------------------------------
    def create_mission(self, title: str, description: str = "", context: Optional[Dict] = None) -> Dict:
        return self._store.create_mission(title, description, context)

    def checkpoint(self, mission_id: str, note: str, state: Optional[Dict] = None) -> Dict:
        """Save a point-in-time snapshot of mission progress. Call this
        whenever meaningful progress happens on a long-running mission
        (a decision made, a sub-goal finished, external info gathered) -
        not on every message, just when losing this would hurt."""
        return self._store.add_checkpoint(mission_id, note, state)

    def link_goal(self, mission_id: str, goal_id: str) -> bool:
        return self._store.link_goal(mission_id, goal_id)

    def pause_mission(self, mission_id: str) -> bool:
        return self._store.update_status(mission_id, "paused")

    def complete_mission(self, mission_id: str) -> bool:
        return self._store.update_status(mission_id, "completed")

    def abandon_mission(self, mission_id: str) -> bool:
        return self._store.update_status(mission_id, "abandoned")

    def touch(self, mission_id: str):
        self._store.touch(mission_id)

    def update_context(self, mission_id: str, context: Dict):
        self._store.update_context(mission_id, context)

    # -- queries ------------------------------------------------------
    def get_mission(self, mission_id: str) -> Optional[Dict]:
        return self._store.get_mission(mission_id)

    def list_active_missions(self) -> List[Dict]:
        return self._store.list_missions(status="active")

    def get_mission_summary(self, mission_id: str) -> Optional[Dict]:
        mission = self._store.get_mission(mission_id)
        if not mission:
            return None
        checkpoints = self._store.get_checkpoints(mission_id, limit=5)
        mission["recent_checkpoints"] = checkpoints
        return mission

    # -- auto-resume --------------------------------------------------
    def get_resumable_mission(self, idle_seconds: int = IDLE_RESUME_SECONDS) -> Optional[Dict]:
        """Most recently active non-terminal mission that's been idle long
        enough to plausibly be "the thing from last time" rather than
        something still open in this same session. Returns None if there's
        nothing to resume - callers should treat that as "nothing to say",
        not an error."""
        active = self._store.list_missions(status="active")
        paused = self._store.list_missions(status="paused")
        candidates = sorted(active + paused, key=lambda m: m["last_active_at"], reverse=True)
        now = time.time()
        for mission in candidates:
            if now - mission["last_active_at"] >= idle_seconds:
                return self.get_mission_summary(mission["id"])
        return None

    def resume_mission(self, mission_id: str) -> Optional[Dict]:
        mission = self._store.get_mission(mission_id)
        if not mission:
            return None
        if mission["status"] == "paused":
            self._store.update_status(mission_id, "active")
        self._store.increment_resumed_count(mission_id)
        return self.get_mission_summary(mission_id)

    def startup_brief(self) -> Optional[str]:
        """One human-readable line for the boot sequence / morning brief -
        'Welcome back - still mid-mission on X, last checkpoint: ...'.
        Returns None when there's nothing resumable so callers can skip
        the mention entirely instead of printing a blank/awkward line."""
        resumable = self.get_resumable_mission()
        if not resumable:
            return None
        last_note = resumable["recent_checkpoints"][0]["note"] if resumable["recent_checkpoints"] else None
        idle_minutes = int((time.time() - resumable["last_active_at"]) / 60)
        base = f"You still have an open mission: \"{resumable['title']}\" (idle {idle_minutes}m)."
        if last_note:
            base += f" Last checkpoint: {last_note}"
        return base


_instance: Optional[MissionManager] = None


def get_mission_manager() -> MissionManager:
    global _instance
    if _instance is None:
        _instance = MissionManager()
    return _instance
