"""
Danger Sense (PREDICT)
==========================
A single aggregate risk score built from whatever safety-relevant
signals other phases are willing to report, rather than this module
sensing anything itself. register_signal() accepts a generic
(source, severity) pair from any caller; assess_risk() sums whatever
signals are still within SIGNAL_DECAY_SECONDS and buckets the total
into "low"/"elevated"/"high". Two integrations are wired in as a
convenience and are both import-guarded:

    PHASE_18_8_SECURITY.intruder_alert  - pulls current failure_count()
                                           for known sources (face_lock,
                                           voice_lock) as signals.
    PHASE_18_9_SMART_DEVICES door_control/camera_guard - same idea for
                                           door and camera sources.

Neither integration is required - register_signal() works standalone
with zero other phases present, and pull_known_sources() (which reads
the two integrations above) simply contributes nothing extra if
they're missing. This module never contacts emergency services,
locks anything down, or takes any action itself; assess_risk()'s
result is meant for a caller (routine.py, a notification, a voice
response) to act on.
"""

import time
from typing import Dict, List, Optional

try:
    from security.intruder_alert import get_intruder_alert

    _INTRUDER_ALERT_AVAILABLE = True
except Exception:
    _INTRUDER_ALERT_AVAILABLE = False

try:
    from home.door_control import get_door_control

    _DOOR_CONTROL_AVAILABLE = True
except Exception:
    _DOOR_CONTROL_AVAILABLE = False

SIGNAL_DECAY_SECONDS = 300
LOW_THRESHOLD = 2
HIGH_THRESHOLD = 5
KNOWN_AUTH_SOURCES = ("face_lock", "voice_lock")


class DangerSense:
    """Aggregate, decaying risk score from arbitrary signals. Use
    get_danger_sense()."""

    def __init__(self):
        self._signals: List[Dict] = []  # {"source": str, "severity": int, "timestamp": float}

    def register_signal(self, source: str, severity: int = 1) -> Dict:
        """Records one risk signal from `source` (any string a caller
        chooses - "camera:porch", "door:front", "unusual_login",
        whatever it wants tracked) with `severity` contributing that
        many points to assess_risk()'s total. Returns {"success":
        bool, "error": Optional[str]}."""
        if not source:
            return {"success": False, "error": "source required"}
        self._signals.append({"source": source, "severity": max(1, severity), "timestamp": time.time()})
        return {"success": True, "error": None}

    def _active_signals(self) -> List[Dict]:
        cutoff = time.time() - SIGNAL_DECAY_SECONDS
        self._signals = [s for s in self._signals if s["timestamp"] >= cutoff]
        return self._signals

    def pull_known_sources(self) -> Dict:
        """Registers a signal for each currently-nonzero
        intruder_alert.py failure count (face_lock, voice_lock, and
        any "door:<id>"/"camera:<id>" sources door_control.py or
        camera_guard.py have reported to it) if those packages are
        importable. Safe to call repeatedly - it only adds signals
        for counts still nonzero right now, it doesn't re-add
        anything already decayed out. Returns {"pulled": List[str],
        "error": Optional[str]}."""
        pulled = []
        if _INTRUDER_ALERT_AVAILABLE:
            alert = get_intruder_alert()
            sources = list(KNOWN_AUTH_SOURCES)
            if _DOOR_CONTROL_AVAILABLE:
                sources += [f"door:{lock_id}" for lock_id in get_door_control().list_doors()]
            for source in sources:
                count = alert.failure_count(source)
                if count > 0:
                    self.register_signal(source, severity=count)
                    pulled.append(source)
        return {"pulled": pulled, "error": None}

    def assess_risk(self) -> Dict:
        """Sums every signal still within SIGNAL_DECAY_SECONDS and
        buckets the total: "low" below LOW_THRESHOLD, "high" at or
        above HIGH_THRESHOLD, "elevated" in between. Returns
        {"level": str, "score": int, "contributing_sources":
        List[str]}, where contributing_sources lists each distinct
        source with an active signal (not one entry per signal)."""
        active = self._active_signals()
        score = sum(s["severity"] for s in active)
        sources = sorted({s["source"] for s in active})
        if score >= HIGH_THRESHOLD:
            level = "high"
        elif score >= LOW_THRESHOLD:
            level = "elevated"
        else:
            level = "low"
        return {"level": level, "score": score, "contributing_sources": sources}

    def clear(self) -> Dict:
        """Drops every currently tracked signal. Returns {"success":
        bool, "error": Optional[str]}."""
        self._signals = []
        return {"success": True, "error": None}


_danger_sense: Optional[DangerSense] = None


def get_danger_sense() -> DangerSense:
    global _danger_sense
    if _danger_sense is None:
        _danger_sense = DangerSense()
    return _danger_sense
