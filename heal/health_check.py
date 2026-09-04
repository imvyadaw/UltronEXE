"""
Health Check (HEAL)
=======================
A latest-status board for whatever components a caller reports on,
mirroring PHASE_18_9_1_AI_EVOLUTION's danger_sense.py pattern: this
module doesn't probe disk space, ping processes, or sense anything on
its own - report() records a caller-supplied ("ok"/"warn"/"fail",
detail) for a named component, and run_check() rolls up the latest
report per component into one overall picture. Whatever wants to
actually watch something (a scheduler polling process.poll(), a
try/except around a risky call, PHASE_18_9_SMART_DEVICES noticing a
device stopped responding) is the one reporting in.

Only the most recent report per component is kept for run_check()'s
verdict - history of every report is still available via
component_history() for a caller that wants the trend, not just the
current state.
"""

import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "SELF_MANAGEMENT_HEALTH_CHECK_FILE"
DEFAULT_STATE_FILE = "data/self_management/health_check.json"
VALID_STATUSES = ("ok", "warn", "fail")
MAX_HISTORY_PER_COMPONENT = 100


class HealthCheck:
    """Latest-status board over caller-reported components. Use
    get_health_check()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"components": {}}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def report(self, component: str, status: str, detail: str = "") -> Dict:
        """Records `status` ("ok"/"warn"/"fail") for `component` right
        now, with an optional free-text `detail`. Each call appends to
        that component's history (capped at
        MAX_HISTORY_PER_COMPONENT, oldest dropped first) and becomes
        the new "latest" for run_check(). Returns {"success": bool,
        "error": Optional[str]}."""
        if not component:
            return {"success": False, "error": "component required"}
        if status not in VALID_STATUSES:
            return {"success": False, "error": f"status must be one of {VALID_STATUSES}"}
        data = self._read_state()
        entry = {"status": status, "detail": detail, "timestamp": time.time()}
        comp = data["components"].setdefault(component, {"history": []})
        comp["history"] = (comp["history"] + [entry])[-MAX_HISTORY_PER_COMPONENT:]
        data["components"][component] = comp
        self._write_state(data)
        return {"success": True, "error": None}

    def run_check(self) -> Dict:
        """Rolls up the latest report per component into one verdict:
        "fail" if any component's latest status is "fail", else "warn"
        if any is "warn", else "ok" (and "unknown" if nothing has ever
        reported in). Returns {"overall": str, "components": {name:
        {"status": str, "detail": str, "timestamp": float}},
        "error": Optional[str]}."""
        data = self._read_state()
        latest = {}
        for name, comp in data["components"].items():
            if comp["history"]:
                latest[name] = comp["history"][-1]
        if not latest:
            overall = "unknown"
        elif any(v["status"] == "fail" for v in latest.values()):
            overall = "fail"
        elif any(v["status"] == "warn" for v in latest.values()):
            overall = "warn"
        else:
            overall = "ok"
        return {"overall": overall, "components": latest, "error": None}

    def component_history(self, component: str, limit: int = 20) -> List[Dict]:
        """Up to `limit` most recent reports for `component`, oldest
        first. Returns an empty list if the component has never
        reported in."""
        data = self._read_state()
        comp = data["components"].get(component)
        if not comp:
            return []
        return comp["history"][-limit:]

    def failing_components(self) -> List[str]:
        """Names of every component whose latest report is "fail",
        sorted. Convenience wrapper over run_check() for a caller
        (auto_fix.py, a notification) that only cares which ones need
        attention."""
        latest = self.run_check()["components"]
        return sorted(name for name, v in latest.items() if v["status"] == "fail")


_health_check: Optional[HealthCheck] = None


def get_health_check() -> HealthCheck:
    global _health_check
    if _health_check is None:
        _health_check = HealthCheck()
    return _health_check
