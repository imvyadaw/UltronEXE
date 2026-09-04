"""
Restart (HEAL)
=================
A gatekeeper for restart requests, not a restarter - this module
never calls os.execv, kills a process, or reloads anything itself.
request_restart() logs that `component` wants restarting and returns
whether it's currently allowed to proceed, based on
MIN_RESTART_INTERVAL_SECONDS and MAX_RESTARTS_PER_WINDOW: too many
requests too close together are refused (allowed=False) so a flapping
component can't loop-restart forever. The actual restart - however
that's done for a given component - is always the caller's job;
this module only answers "should I, and how many times has this
happened."
"""

import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_RESTART_FILE"
DEFAULT_STATE_FILE = "data/self_management/restart.json"
MIN_RESTART_INTERVAL_SECONDS = 60
MAX_RESTARTS_PER_WINDOW = 5
WINDOW_SECONDS = 3600


class Restart:
    """Restart-request gatekeeper and log. Use get_restart(). Never
    restarts anything itself."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"log": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def request_restart(self, component: str, reason: str = "") -> Dict:
        """Logs a restart request for `component` and decides whether
        it's currently allowed: refused if the last request for this
        component was under MIN_RESTART_INTERVAL_SECONDS ago, or if
        MAX_RESTARTS_PER_WINDOW requests have already landed within
        WINDOW_SECONDS (a flap-loop guard). The request is logged
        either way, so the caller can inspect restart_log() even for
        refused attempts. Returns {"allowed": bool, "reason": str,
        "error": Optional[str]}."""
        if not component:
            return {"allowed": False, "reason": "component required", "error": "component required"}
        data = self._read_state()
        history = data["log"].setdefault(component, [])
        now = time.time()

        decision = "allowed"
        if history and (now - history[-1]["timestamp"]) < MIN_RESTART_INTERVAL_SECONDS:
            decision = "too soon since last request"
        else:
            recent = [h for h in history if now - h["timestamp"] < WINDOW_SECONDS]
            if len(recent) >= MAX_RESTARTS_PER_WINDOW:
                decision = "too many restarts in window - possible flap loop"

        history.append({"reason": reason, "timestamp": now, "decision": decision})
        self._write_state(data)
        return {"allowed": decision == "allowed", "reason": decision, "error": None}

    def restart_log(self, component: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Up to `limit` most recent restart requests, oldest first,
        optionally filtered to a single `component`. Each entry
        includes whether it was allowed via its "decision" field."""
        data = self._read_state()
        if component is not None:
            entries = data["log"].get(component, [])
        else:
            entries = sorted(
                (dict(e, component=c) for c, hist in data["log"].items() for e in hist),
                key=lambda e: e["timestamp"],
            )
        return entries[-limit:]

    def restart_count(self, component: str, window_seconds: int = WINDOW_SECONDS) -> int:
        """How many restart requests `component` has made within the
        last `window_seconds`, regardless of whether each was
        allowed."""
        history = self._read_state()["log"].get(component, [])
        cutoff = time.time() - window_seconds
        return sum(1 for h in history if h["timestamp"] >= cutoff)


_restart: Optional[Restart] = None


def get_restart() -> Restart:
    global _restart
    if _restart is None:
        _restart = Restart()
    return _restart
