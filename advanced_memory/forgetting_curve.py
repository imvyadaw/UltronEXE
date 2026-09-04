"""
Forgetting curve
================
Ebbinghaus-style memory strength: every memory (an episodic event, a
concept, a place, a routine) decays over time unless it keeps getting
accessed, in which case it gets harder to forget - the same
spaced-repetition idea flashcard apps use. Nothing else in
PHASE_17_3_MEMORY_SYSTEM/ or memory/ has a notion of "how likely is
this to still matter" - episodic/semantic/spatial/temporal memory
would otherwise grow forever with no signal for what's safe to prune.
That signal is what this module provides; memory_consolidator.py is
the only caller that acts on it (pruning is a deliberate decision made
during a consolidation pass, never something this module does on its
own - retention() is read-only).

retention(t) = e^(-t / strength), t and strength both in days.
`strength` starts small (a one-off event decays fast) and grows each
time record_access() is called (repeated recall -> slower decay),
mirroring how real spaced repetition works.
"""

import math
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "forgetting_curve.db"

SECONDS_PER_DAY = 86400.0
MIN_STRENGTH_DAYS = 0.5
MAX_STRENGTH_DAYS = 90.0
ACCESS_GROWTH_FACTOR = 1.4  # each access multiplies strength, diminishing near MAX_STRENGTH_DAYS
DEFAULT_FORGET_THRESHOLD = 0.15

_curve: Optional["ForgettingCurve"] = None
_lock = Lock()


class ForgettingCurve:
    """Tracks a decaying strength per memory_ref ("episodic:42",
    "concept:vpn", ...). Do not construct directly - use
    get_forgetting_curve()."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS strengths (
                memory_ref TEXT PRIMARY KEY,
                strength_days REAL,
                importance REAL,
                access_count INTEGER,
                created_at REAL,
                last_accessed REAL
            )""")
        self._conn.commit()
        self._write_lock = Lock()

    def track(self, memory_ref: str, importance: float = 0.5) -> Dict:
        """Start tracking a new memory. `importance` (0-1, caller's own
        judgment - e.g. episodic_memory.py passing through the caller's
        importance= argument) sets the initial strength so an
        important first-time memory starts out harder to forget than a
        throwaway one, without either needing a single access yet."""
        importance = max(0.0, min(1.0, importance))
        strength = MIN_STRENGTH_DAYS + importance * 4.0
        now = time.time()
        try:
            with self._write_lock:
                self._conn.execute(
                    "INSERT INTO strengths (memory_ref, strength_days, importance, access_count, created_at, last_accessed) "
                    "VALUES (?, ?, ?, 0, ?, ?) "
                    "ON CONFLICT(memory_ref) DO NOTHING",
                    (memory_ref, strength, importance, now, now),
                )
                self._conn.commit()
            return {"success": True, "memory_ref": memory_ref, "strength_days": round(strength, 3)}
        except Exception as e:
            return {"error": str(e)}

    def record_access(self, memory_ref: str) -> Dict:
        """Call whenever a memory is actually recalled (not just
        listed) - reinforces it, same as re-seeing a flashcard resets
        and extends its interval."""
        try:
            row = self._get_row(memory_ref)
            if row is None:
                # first-ever access of something never explicitly track()ed -
                # start it at neutral importance rather than erroring.
                self.track(memory_ref, importance=0.5)
                row = self._get_row(memory_ref)
            new_strength = min(MAX_STRENGTH_DAYS, row["strength_days"] * ACCESS_GROWTH_FACTOR)
            with self._write_lock:
                self._conn.execute(
                    "UPDATE strengths SET strength_days = ?, access_count = access_count + 1, last_accessed = ? WHERE memory_ref = ?",
                    (new_strength, time.time(), memory_ref),
                )
                self._conn.commit()
            return {"success": True, "memory_ref": memory_ref, "strength_days": round(new_strength, 3)}
        except Exception as e:
            return {"error": str(e)}

    def boost(self, memory_ref: str, amount_days: float) -> Dict:
        """Direct reinforcement outside normal access, e.g.
        memory_consolidator.py protecting a memory it just promoted to
        semantic memory so it isn't immediately re-flagged forgettable."""
        try:
            row = self._get_row(memory_ref)
            if row is None:
                return {"error": f"'{memory_ref}' is not tracked"}
            new_strength = min(MAX_STRENGTH_DAYS, row["strength_days"] + amount_days)
            with self._write_lock:
                self._conn.execute(
                    "UPDATE strengths SET strength_days = ? WHERE memory_ref = ?", (new_strength, memory_ref)
                )
                self._conn.commit()
            return {"success": True, "memory_ref": memory_ref, "strength_days": round(new_strength, 3)}
        except Exception as e:
            return {"error": str(e)}

    def retention(self, memory_ref: str, at_time: Optional[float] = None) -> Dict:
        """Current retention score in [0, 1] - e^(-t/strength) where t
        is days since last_accessed. 1.0 = perfectly fresh, near 0 =
        essentially forgotten."""
        row = self._get_row(memory_ref)
        if row is None:
            return {"error": f"'{memory_ref}' is not tracked"}
        now = at_time if at_time is not None else time.time()
        t_days = max(0.0, (now - row["last_accessed"]) / SECONDS_PER_DAY)
        score = math.exp(-t_days / row["strength_days"])
        return {
            "memory_ref": memory_ref,
            "retention": round(score, 4),
            "days_since_access": round(t_days, 2),
            "strength_days": round(row["strength_days"], 3),
            "access_count": row["access_count"],
        }

    def get_forgettable(
        self, threshold: float = DEFAULT_FORGET_THRESHOLD, ref_prefix: Optional[str] = None, limit: int = 50
    ) -> Dict:
        """Every tracked memory currently below `threshold` retention,
        weakest first - candidates for memory_consolidator.py to prune.
        `ref_prefix` narrows to one memory type, e.g. "episodic:"."""
        try:
            cur = self._conn.cursor()
            if ref_prefix:
                cur.execute("SELECT memory_ref FROM strengths WHERE memory_ref LIKE ?", (f"{ref_prefix}%",))
            else:
                cur.execute("SELECT memory_ref FROM strengths")
            refs = [r[0] for r in cur.fetchall()]
            now = time.time()
            scored = []
            for ref in refs:
                info = self.retention(ref, at_time=now)
                if "error" not in info and info["retention"] < threshold:
                    scored.append(info)
            scored.sort(key=lambda x: x["retention"])
            return {"threshold": threshold, "count": len(scored[:limit]), "candidates": scored[:limit]}
        except Exception as e:
            return {"error": str(e)}

    def forget(self, memory_ref: str) -> Dict:
        """Stop tracking a memory entirely (call after actually pruning
        it elsewhere - this module never deletes the underlying memory
        itself)."""
        try:
            with self._write_lock:
                cur = self._conn.execute("DELETE FROM strengths WHERE memory_ref = ?", (memory_ref,))
                self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"'{memory_ref}' is not tracked"}
            return {"success": True, "untracked": memory_ref}
        except Exception as e:
            return {"error": str(e)}

    # -- internal --------------------------------------------------------------
    def _get_row(self, memory_ref: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT strength_days, importance, access_count, created_at, last_accessed FROM strengths WHERE memory_ref = ?",
            (memory_ref,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "strength_days": row[0],
            "importance": row[1],
            "access_count": row[2],
            "created_at": row[3],
            "last_accessed": row[4],
        }


def get_forgetting_curve() -> ForgettingCurve:
    """Process-wide singleton, same pattern as memory_graph.get_memory_graph()."""
    global _curve
    with _lock:
        if _curve is None:
            _curve = ForgettingCurve()
        return _curve
