"""
World State (Phase 19.1)
=========================
A live, queryable model of "what is true right now" for Ultron to
reason and plan against - backed by a single shared database at
database/world_state.db:

    pc_state.py          - machine state: OS/host, CPU/RAM/disk, battery
    active_context.py    - what's currently focused on + user idle/active
    task_state.py         - tracked tasks and their pending/active/done status
    device_state.py       - registry of known devices and connection status
    environment_state.py  - ambient context: time of day, connectivity, misc facts
    context_snapshot.py   - consolidates all of the above into one snapshot,
                             persisted with history and before/after diffing
    world_state_manager.py - single entry point that owns one instance of
                             each of the above and ties them together

Usage:
    from intelligence.world_state import get_world_state_manager
    wsm = get_world_state_manager()
    wsm.capture_full_state()

Each sub-module also exposes its own get_x() singleton and can be used
directly (e.g. `from intelligence.world_state import get_task_state`)
without going through the manager.

Purely additive - nothing in Phase 1-18 imports from here.
"""

from intelligence.world_state.active_context import ActiveContext, get_active_context
from intelligence.world_state.context_snapshot import ContextSnapshot, get_context_snapshot
from intelligence.world_state.device_state import DeviceState, get_device_state
from intelligence.world_state.environment_state import EnvironmentState, get_environment_state
from intelligence.world_state.pc_state import PCState, get_pc_state
from intelligence.world_state.task_state import TaskState, get_task_state
from intelligence.world_state.world_state_manager import WorldStateManager, get_world_state_manager

__all__ = [
    "PCState",
    "get_pc_state",
    "ActiveContext",
    "get_active_context",
    "TaskState",
    "get_task_state",
    "DeviceState",
    "get_device_state",
    "EnvironmentState",
    "get_environment_state",
    "ContextSnapshot",
    "get_context_snapshot",
    "WorldStateManager",
    "get_world_state_manager",
]
