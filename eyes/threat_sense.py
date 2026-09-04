"""
Threat Sense
============
"Threat" here means an everyday home-safety hazard, not an
adversarial one - this module has no notion of weapons, no
person-targeting logic, and no classification more specific than the
three checks below. That scope is deliberate, the same way
place_memory.py stays exact/radius-match instead of fuzzy: a
false-confident "armed" or "hostile" label would be far worse than no
label, and this project has no dataset or model that could back one up
honestly anyway. What it does check, cheaply:

  1. motion_spike   - big frame-to-frame pixel difference (something
                       moved fast/suddenly), via simple absdiff, no
                       optical flow.
  2. fire_signal     - a meaningful fraction of the frame is both
                       bright and in the orange/red hue band. A crude
                       proxy for fire/flame, not a fire-detection
                       model - false positives (sunset light, orange
                       decor) are expected and should be treated as
                       "worth a look", not "call the fire department".
  3. unrecognized_person - face_scanner finds a face but
                       MEMORY/face_memory.recognize() has no name for
                       its embedding_id. This is the one check that
                       reaches into MEMORY/, done the same lazy-import,
                       best-effort way COMMAND/ modules already reach
                       into MEMORY/ and CORE/.

Every finding carries a "level" of "low" or "medium", never "high" -
this module flags, it doesn't conclude, and DISPLAY/danger_alert.py
(or a human) decides what if anything to do about a flag. Findings are
logged to storage/sqlite/threat_log.db purely as a record of what was
flagged and when; nothing here calls out, dials, or notifies on its
own.
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    import cv2
    import numpy as np

    _CV2_AVAILABLE = True
except Exception:
    _CV2_AVAILABLE = False

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "threat_log.db"

MOTION_DIFF_THRESHOLD = 40  # 0-255 pixel-diff mean above which a frame pair counts as a motion spike
FIRE_MIN_FRACTION = 0.06  # fraction of frame that must match the fire heuristic to flag


class ThreatSense:
    """Generic hazard heuristics over a frame (+ optional previous frame). Use get_threat_sense()."""

    def __init__(self):
        self._db_ok = True
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT, level TEXT, detail TEXT, logged_at REAL
                )""")
            self._conn.commit()
        except Exception:
            self._db_ok = False
            self._fallback: List[Dict] = []

    def assess(self, frame, previous_frame=None) -> List[Dict]:
        """Runs every available check and returns the findings (each
        logged as a side effect). Empty list means "nothing flagged",
        which is also what a missing frame or unavailable backend
        returns - assess() never distinguishes "checked, all clear"
        from "couldn't check" in its return value; call is_available()
        first if that distinction matters to the caller."""
        if frame is None:
            return []
        findings: List[Dict] = []

        motion = self._check_motion(frame, previous_frame)
        if motion:
            findings.append(motion)

        fire = self._check_fire_signal(frame)
        if fire:
            findings.append(fire)

        stranger = self._check_unrecognized_person(frame)
        if stranger:
            findings.append(stranger)

        for f in findings:
            self._log(f["kind"], f["level"], f.get("detail", ""))
        return findings

    def is_available(self) -> bool:
        return _CV2_AVAILABLE

    # -- checks --------------------------------------------------------
    def _check_motion(self, frame, previous_frame) -> Optional[Dict]:
        if not _CV2_AVAILABLE or previous_frame is None:
            return None
        try:
            g1 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            g2 = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
            if g1.shape != g2.shape:
                return None
            diff = cv2.absdiff(g1, g2)
            score = float(diff.mean())
            if score >= MOTION_DIFF_THRESHOLD:
                return {"kind": "motion_spike", "level": "low", "detail": f"diff_mean={score:.1f}"}
            return None
        except Exception:
            return None

    def _check_fire_signal(self, frame) -> Optional[Dict]:
        if not _CV2_AVAILABLE:
            return None
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower = np.array([5, 120, 150])
            upper = np.array([30, 255, 255])
            mask = cv2.inRange(hsv, lower, upper)
            fraction = float((mask > 0).mean())
            if fraction >= FIRE_MIN_FRACTION:
                return {"kind": "fire_signal", "level": "medium", "detail": f"fraction={fraction:.3f}"}
            return None
        except Exception:
            return None

    def _check_unrecognized_person(self, frame) -> Optional[Dict]:
        try:
            from eyes.face_scanner import get_face_scanner
            from memory.face_memory import get_face_memory

            scanner = get_face_scanner()
            boxes = scanner.detect_faces(frame)
            if not boxes:
                return None
            embedding_id = scanner.embedding_id(frame, box=boxes[0])
            if not embedding_id:
                return None
            name = get_face_memory().recognize(embedding_id)
            if name is None:
                return {"kind": "unrecognized_person", "level": "low", "detail": f"embedding_id={embedding_id}"}
            return None
        except Exception:
            return None

    # -- log -------------------------------------------------------------
    def _log(self, kind: str, level: str, detail: str) -> None:
        now = time.time()
        if not self._db_ok:
            self._fallback.append({"kind": kind, "level": level, "detail": detail, "logged_at": now})
            return
        self._conn.execute(
            "INSERT INTO findings (kind, level, detail, logged_at) VALUES (?, ?, ?, ?)",
            (kind, level, detail, now),
        )
        self._conn.commit()

    def recent_findings(self, limit: int = 20) -> List[Dict]:
        if not self._db_ok:
            return self._fallback[-limit:]
        cur = self._conn.cursor()
        cur.execute("SELECT kind, level, detail, logged_at FROM findings ORDER BY logged_at DESC LIMIT ?", (limit,))
        cols = ["kind", "level", "detail", "logged_at"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


_threat_sense: Optional[ThreatSense] = None


def get_threat_sense() -> ThreatSense:
    global _threat_sense
    if _threat_sense is None:
        _threat_sense = ThreatSense()
    return _threat_sense
