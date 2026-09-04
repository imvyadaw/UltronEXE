"""
Threshold Manager (Phase 19.8 - Confidence Engine)
==================================================
Persistent home for the two confidence thresholds decision_gate.py
checks a score against: threshold_auto (confidence at or above this
-> auto_execute) and threshold_confirm (at or above this but below
threshold_auto -> confirm_with_user; below it -> decline). Hardcoded
defaults exist per risk_level so the system works with an empty
database, but any row actually stored - either a per-action_type
override or a per-risk_level default - takes precedence. Purely a
record-keeper, same spirit as skill_store.py in Phase 19.6: it
doesn't decide when thresholds should change (confidence_learner.py's
job), just stores whatever it's told and always enforces
threshold_confirm <= threshold_auto so decision_gate.py never sees an
inverted pair.

Storage: database/confidence_history.db, table confidence_thresholds.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "confidence_history.db"

_instance: Optional["ThresholdManager"] = None
_instance_lock = threading.Lock()

# fallback when nothing's stored yet for a risk_level - critical stays
# nearly impossible to auto-execute on purpose
_HARDCODED_DEFAULTS = {
    "low": {"threshold_auto": 0.55, "threshold_confirm": 0.30},
    "medium": {"threshold_auto": 0.75, "threshold_confirm": 0.50},
    "high": {"threshold_auto": 0.90, "threshold_confirm": 0.70},
    "critical": {"threshold_auto": 0.99, "threshold_confirm": 0.85},
}

# SQLite treats every NULL as distinct for UNIQUE purposes, so two
# "no action_type" rows for the same risk_level would silently both
# insert instead of conflicting. Store the risk_level-default row
# under this sentinel instead of NULL, and translate back to None at
# the API boundary so callers never see the sentinel.
_NO_ACTION_TYPE = ""


def _key(action_type: Optional[str]) -> str:
    return action_type if action_type else _NO_ACTION_TYPE


def _unkey(action_type: str) -> Optional[str]:
    return action_type if action_type else None


class ThresholdManager:
    """Stores and serves confidence_auto/confidence_confirm pairs,
    optionally scoped to a specific action_type on top of a
    risk_level's default."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS confidence_thresholds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                risk_level TEXT,
                action_type TEXT,
                threshold_auto REAL,
                threshold_confirm REAL,
                updated_at REAL,
                UNIQUE(risk_level, action_type)
            )""")
        self._conn.commit()

    def get_thresholds(self, risk_level: str, action_type: Optional[str] = None) -> Dict:
        """Precedence: a stored (risk_level, action_type) override,
        then a stored (risk_level, NULL) default, then the hardcoded
        default for that risk_level."""
        if action_type:
            row = self._select(risk_level, action_type)
            if row:
                return row
        row = self._select(risk_level, None)
        if row:
            return row
        fallback = _HARDCODED_DEFAULTS.get(risk_level, _HARDCODED_DEFAULTS["medium"])
        return {
            "risk_level": risk_level,
            "action_type": action_type,
            "threshold_auto": fallback["threshold_auto"],
            "threshold_confirm": fallback["threshold_confirm"],
            "source": "hardcoded_default",
        }

    def set_thresholds(
        self, risk_level: str, threshold_auto: float, threshold_confirm: float, action_type: Optional[str] = None
    ) -> Dict:
        threshold_auto = max(0.0, min(1.0, threshold_auto))
        threshold_confirm = max(0.0, min(threshold_auto, threshold_confirm))
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO confidence_thresholds
                   (risk_level, action_type, threshold_auto, threshold_confirm, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(risk_level, action_type) DO UPDATE SET
                       threshold_auto = excluded.threshold_auto,
                       threshold_confirm = excluded.threshold_confirm,
                       updated_at = excluded.updated_at""",
                (risk_level, _key(action_type), threshold_auto, threshold_confirm, now),
            )
            self._conn.commit()
        return self.get_thresholds(risk_level, action_type)

    def adjust_thresholds(
        self, risk_level: str, action_type: Optional[str] = None, delta_auto: float = 0.0, delta_confirm: float = 0.0
    ) -> Dict:
        """Nudge whatever's currently in effect (stored or hardcoded)
        by a delta - what confidence_learner.py calls when a pattern
        of outcomes says the current bar is mis-set, without needing
        to know the absolute values itself."""
        current = self.get_thresholds(risk_level, action_type)
        return self.set_thresholds(
            risk_level,
            current["threshold_auto"] + delta_auto,
            current["threshold_confirm"] + delta_confirm,
            action_type=action_type,
        )

    def list_thresholds(self) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute("""SELECT risk_level, action_type, threshold_auto, threshold_confirm, updated_at
                   FROM confidence_thresholds ORDER BY risk_level, action_type""").fetchall()
        return [
            {
                "risk_level": r[0],
                "action_type": _unkey(r[1]),
                "threshold_auto": r[2],
                "threshold_confirm": r[3],
                "updated_at": r[4],
                "source": "stored",
            }
            for r in rows
        ]

    def reset_to_default(self, risk_level: str, action_type: Optional[str] = None) -> Dict:
        with self._lock:
            self._conn.execute(
                "DELETE FROM confidence_thresholds WHERE risk_level = ? AND action_type = ?",
                (risk_level, _key(action_type)),
            )
            self._conn.commit()
        return self.get_thresholds(risk_level, action_type)

    def _select(self, risk_level: str, action_type: Optional[str]) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT risk_level, action_type, threshold_auto, threshold_confirm, updated_at
                   FROM confidence_thresholds WHERE risk_level = ? AND action_type = ?""",
                (risk_level, _key(action_type)),
            ).fetchone()
        if row is None:
            return None
        return {
            "risk_level": row[0],
            "action_type": _unkey(row[1]),
            "threshold_auto": row[2],
            "threshold_confirm": row[3],
            "updated_at": row[4],
            "source": "stored",
        }


def get_hardcoded_default(risk_level: str) -> Dict:
    """The original, never-persisted floor for a risk_level - what
    get_thresholds() falls back to when nothing's stored, and what
    confidence_learner.py treats as the safety floor it will never
    ease threshold_auto below no matter how good the track record
    looks."""
    fallback = _HARDCODED_DEFAULTS.get(risk_level, _HARDCODED_DEFAULTS["medium"])
    return dict(fallback)


def get_threshold_manager() -> ThresholdManager:
    """Process-wide ThresholdManager singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ThresholdManager()
    return _instance
