"""
State Manager
=============
Persists Ultron's session-level state (runtime modes, active workflow,
last active app/directory, arbitrary key/value scratch state) to a JSON
file under storage/cache/, so it survives process restarts. Other
singletons in core/ (task_queue, workflow_engine) use this to save/restore
their own state instead of each rolling their own file I/O.

Usage:
    from core.state_manager import get_state_manager
    sm = get_state_manager()
    sm.set("last_workflow", "morning_routine")
    sm.get("last_workflow")
    sm.save()   # flush to disk (also called automatically on set())
"""

import json
import threading
import time
from typing import Any, Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.state_manager")

_manager: Optional["StateManager"] = None
_lock = threading.Lock()


class StateManager:
    """Thread-safe key/value session state, auto-persisted to disk."""

    def __init__(self):
        from config import CACHE_DIR

        self._path = CACHE_DIR / "ultron_state.json"
        self._state: Dict[str, Any] = {}
        self._io_lock = threading.Lock()
        self._load()

    # -- persistence -------------------------------------------------
    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state file, starting fresh: {e}")
                self._state = {}
        else:
            self._state = {}

    def save(self) -> Dict:
        """Flush current state to disk."""
        try:
            with self._io_lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self._path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, indent=2, default=str)
                tmp_path.replace(self._path)
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return {"error": str(e)}

    # -- key/value scratch state --------------------------------------
    def set(self, key: str, value: Any, persist: bool = True) -> None:
        self._state[key] = value
        self._state.setdefault("_meta", {})["last_updated"] = time.time()
        if persist:
            self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def delete(self, key: str, persist: bool = True) -> None:
        self._state.pop(key, None)
        if persist:
            self.save()

    def all(self) -> Dict:
        return dict(self._state)

    # -- namespaced sections (e.g. per-module state) -------------------
    def get_section(self, section: str) -> Dict:
        return dict(self._state.get(section, {}))

    def set_section(self, section: str, data: Dict, persist: bool = True) -> None:
        self._state[section] = data
        if persist:
            self.save()

    def update_section(self, section: str, key: str, value: Any, persist: bool = True) -> None:
        self._state.setdefault(section, {})[key] = value
        if persist:
            self.save()

    # -- runtime session snapshot (modes, active app/dir) ---------------
    def save_session(self, **fields) -> Dict:
        """Convenience for UltronRuntime to persist its toggleable modes
        (ui_enabled, text_mode_enabled, silent_mode, ...) each time one
        changes, so a restart can (optionally) restore them."""
        self.set_section("session", fields)
        return {"success": True, "session": fields}

    def load_session(self) -> Dict:
        return self.get_section("session")


def get_state_manager() -> StateManager:
    """Process-wide singleton, same pattern as core.events.get_event_bus()."""
    global _manager
    with _lock:
        if _manager is None:
            _manager = StateManager()
        return _manager
