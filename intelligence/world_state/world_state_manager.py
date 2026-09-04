"""
World State Manager (Phase 19.1 - World State)
=================================================
Single entry point for the whole world_state/ package: owns one
instance of each sub-state (pc_state, active_context, task_state,
device_state, environment_state, context_snapshot) and exposes them
as properties, plus a capture_full_state() convenience method and an
optional background thread that captures on an interval so the rest
of Ultron doesn't have to remember to. All six sub-modules share the
one database/world_state.db file (each owns its own table); nothing
outside this package needs to know that - go through
get_world_state_manager() and its properties.

Usage:
    from intelligence.world_state.world_state_manager import get_world_state_manager
    wsm = get_world_state_manager()
    wsm.pc.capture()
    wsm.tasks.create_task("Deploy build")
    state = wsm.capture_full_state()          # one-off consolidated snapshot
    wsm.start_auto_capture(interval_seconds=60)  # keep it fresh in the background
"""

import threading
from typing import Dict, Optional

from core.logger import get_logger
from intelligence.world_state.active_context import ActiveContext, get_active_context
from intelligence.world_state.context_snapshot import ContextSnapshot, get_context_snapshot
from intelligence.world_state.device_state import DeviceState, get_device_state
from intelligence.world_state.environment_state import EnvironmentState, get_environment_state
from intelligence.world_state.pc_state import PCState, get_pc_state
from intelligence.world_state.task_state import TaskState, get_task_state

logger = get_logger("ultron.world_state")

DEFAULT_AUTO_CAPTURE_INTERVAL_SECONDS = 60

_instance: Optional["WorldStateManager"] = None
_instance_lock = threading.Lock()


class WorldStateManager:
    """Orchestrates the six world-state sub-modules as one unit."""

    def __init__(
        self,
        pc: Optional[PCState] = None,
        active_context: Optional[ActiveContext] = None,
        tasks: Optional[TaskState] = None,
        devices: Optional[DeviceState] = None,
        environment: Optional[EnvironmentState] = None,
        snapshots: Optional[ContextSnapshot] = None,
    ):
        self.pc = pc or get_pc_state()
        self.active_context = active_context or get_active_context()
        self.tasks = tasks or get_task_state()
        self.devices = devices or get_device_state()
        self.environment = environment or get_environment_state()
        self.snapshots = snapshots or get_context_snapshot()

        self._auto_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # -- consolidated access ------------------------------------------------
    def capture_full_state(self) -> Dict:
        """Take a fresh PC-state reading, build a consolidated snapshot of
        every sub-state, persist it, and return it."""
        try:
            self.pc.capture()
        except Exception as e:
            logger.warning(f"pc_state capture failed during capture_full_state: {e}")
        result = self.snapshots.save()
        return result.get("snapshot", {})

    def get_state(self, section: Optional[str] = None) -> Dict:
        """Convenience accessor: get_state() returns the full latest
        consolidated snapshot (building one if none has been saved yet);
        get_state('pc'|'active_context'|'active_tasks'|'connected_devices'|
        'environment') returns just that section."""
        latest = self.snapshots.latest()
        snapshot = latest["snapshot"] if latest else self.snapshots.build()
        if section is None:
            return snapshot
        if section not in snapshot:
            return {"error": f"unknown section '{section}'"}
        return snapshot[section]

    # -- background auto-capture -----------------------------------------------
    def start_auto_capture(self, interval_seconds: int = DEFAULT_AUTO_CAPTURE_INTERVAL_SECONDS) -> Dict:
        """Start a daemon thread that calls capture_full_state() every
        interval_seconds. No-op if already running."""
        if self._auto_thread is not None and self._auto_thread.is_alive():
            return {"success": False, "error": "auto-capture already running"}

        self._stop_event.clear()

        def _loop():
            while not self._stop_event.is_set():
                try:
                    self.capture_full_state()
                except Exception as e:
                    logger.error(f"world_state auto-capture failed: {e}")
                self._stop_event.wait(interval_seconds)

        self._auto_thread = threading.Thread(target=_loop, daemon=True, name="world_state_auto_capture")
        self._auto_thread.start()
        logger.info(f"world_state auto-capture started (every {interval_seconds}s)")
        return {"success": True, "interval_seconds": interval_seconds}

    def stop_auto_capture(self) -> Dict:
        """Stop the background auto-capture thread, if running."""
        if self._auto_thread is None or not self._auto_thread.is_alive():
            return {"success": False, "error": "auto-capture not running"}
        self._stop_event.set()
        self._auto_thread.join(timeout=5)
        logger.info("world_state auto-capture stopped")
        return {"success": True}


def get_world_state_manager() -> WorldStateManager:
    """Process-wide WorldStateManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WorldStateManager()
    return _instance
