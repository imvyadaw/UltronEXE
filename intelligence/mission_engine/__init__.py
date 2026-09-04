"""
Mission Engine (P1 - Mission Persistence Engine)
=================================================
Cross-session persistence layer sitting above intelligence.goal_manager:

    mission_store.py    - sqlite CRUD for missions, checkpoints, events
    mission_manager.py  - lifecycle API + startup auto-resume

Usage:
    from intelligence.mission_engine import get_mission_manager
    mm = get_mission_manager()
    mission = mm.create_mission("Plan the Bangalore trip")
    mm.checkpoint(mission["id"], "Booked flights for Nov 12")
    mm.link_goal(mission["id"], some_goal_id)   # tie to a goal_manager Goal
    ...
    brief = mm.startup_brief()   # None, or a one-line "welcome back" string

Purely additive - nothing elsewhere imports from here yet; wired into
core/executor.py's tool_map, ai/tools_schema.py, and core/assistant.py's
startup sequence (see MANIFEST.md in this folder).
"""

from intelligence.mission_engine.mission_store import MissionStore, get_mission_store
from intelligence.mission_engine.mission_manager import MissionManager, get_mission_manager

__all__ = ["MissionStore", "get_mission_store", "MissionManager", "get_mission_manager"]
