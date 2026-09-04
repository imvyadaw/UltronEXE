"""
Skill Store (Phase 19.6 - Skill Builder)
==================================================
Persistent home for every skill skill_generator.py produces: the
definition itself (name/description/steps), its lifecycle status
(suggested -> active -> deprecated), and a running success/failure
tally with a derived confidence score. Purely a record-keeper - it
doesn't generate, run, or improve skills, just stores them and
answers "what do we know about this skill". Every record_usage()
call re-checks the promote/deprecate thresholds itself, so status
stays current even if nothing ever calls skill_improver.py's
review()/apply() explicitly.

Storage: database/learned_skills.db, table learned_skills.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "learned_skills.db"

_instance: Optional["SkillStore"] = None
_instance_lock = threading.Lock()

STATUS_SUGGESTED = "suggested"
STATUS_ACTIVE = "active"
STATUS_DEPRECATED = "deprecated"

_PROMOTE_AT_SUCCESSES = 3  # suggested -> active after this many clean successes
_DEPRECATE_AT_FAILURE_RATE = 0.5  # deprecate once failure rate crosses this...
_DEPRECATE_MIN_USES = 4  # ...but only once there's been enough use to trust the rate


class SkillStore:
    """CRUD + usage tracking for learned skills."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS learned_skills (
                skill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                steps_json TEXT,
                source TEXT,
                status TEXT DEFAULT 'suggested',
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                created_at REAL,
                updated_at REAL
            )""")
        # Generic outcome log for anything reported by *name* rather than
        # skill_id - e.g. intelligence_core.record_provider_call(skill=...)
        # reporting a plain tool name like "youtube_play", which was never
        # built into a learned_skills row via the recording/detection
        # pipeline above. Kept as its own table rather than folding into
        # learned_skills so a bare tool name never gets treated as (or
        # confused with) an actual generated skill.
        self._conn.execute("""CREATE TABLE IF NOT EXISTS tool_outcomes (
                name TEXT PRIMARY KEY,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                last_context TEXT,
                updated_at REAL
            )""")
        self._conn.commit()

    def save_skill(self, skill: Dict) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO learned_skills
                   (name, description, steps_json, source, status, success_count,
                    failure_count, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)""",
                (
                    skill["name"],
                    skill.get("description", ""),
                    json.dumps(skill.get("steps", [])),
                    skill.get("source", "manual"),
                    STATUS_SUGGESTED,
                    skill.get("confidence", 0.0),
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_skill(self, skill_id: int) -> Optional[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT skill_id, name, description, steps_json, source, status,
                          success_count, failure_count, confidence, created_at, updated_at
                   FROM learned_skills WHERE skill_id = ?""",
                (skill_id,),
            )
            row = cur.fetchone()
        return self._row_to_skill(row) if row else None

    def find_by_name(self, name: str) -> Optional[Dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT skill_id, name, description, steps_json, source, status,
                          success_count, failure_count, confidence, created_at, updated_at
                   FROM learned_skills WHERE name = ? ORDER BY skill_id DESC LIMIT 1""",
                (name,),
            )
            row = cur.fetchone()
        return self._row_to_skill(row) if row else None

    def list_skills(self, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
        with self._lock:
            if status:
                cur = self._conn.execute(
                    """SELECT skill_id, name, description, steps_json, source, status,
                              success_count, failure_count, confidence, created_at, updated_at
                       FROM learned_skills WHERE status = ? ORDER BY confidence DESC, skill_id DESC LIMIT ?""",
                    (status, limit),
                )
            else:
                cur = self._conn.execute(
                    """SELECT skill_id, name, description, steps_json, source, status,
                              success_count, failure_count, confidence, created_at, updated_at
                       FROM learned_skills ORDER BY confidence DESC, skill_id DESC LIMIT ?""",
                    (limit,),
                )
            rows = cur.fetchall()
        return [self._row_to_skill(r) for r in rows]

    def record_usage(self, skill_id: int, success: bool) -> Optional[Dict]:
        """Bump success/failure, recompute confidence, and apply the
        promote/deprecate rules. Returns the updated skill, or None if
        skill_id doesn't exist."""
        skill = self.get_skill(skill_id)
        if skill is None:
            return None

        success_count = skill["success_count"] + (1 if success else 0)
        failure_count = skill["failure_count"] + (0 if success else 1)
        total = success_count + failure_count
        confidence = success_count / total if total else 0.0

        status = skill["status"]
        if status == STATUS_SUGGESTED and success_count >= _PROMOTE_AT_SUCCESSES and failure_count == 0:
            status = STATUS_ACTIVE
        if total >= _DEPRECATE_MIN_USES and (failure_count / total) >= _DEPRECATE_AT_FAILURE_RATE:
            status = STATUS_DEPRECATED

        now = time.time()
        with self._lock:
            self._conn.execute(
                """UPDATE learned_skills SET success_count = ?, failure_count = ?,
                   confidence = ?, status = ?, updated_at = ? WHERE skill_id = ?""",
                (success_count, failure_count, confidence, status, now, skill_id),
            )
            self._conn.commit()
        return self.get_skill(skill_id)

    def record_tool_outcome(self, name: str, success: bool, context: Optional[Dict] = None) -> Dict:
        """Same bookkeeping as record_usage() above, but keyed by a plain
        tool name instead of a learned_skills skill_id - for callers (like
        intelligence_core.record_provider_call) that only know a tool's
        name, not whether it was ever turned into a stored skill."""
        now = time.time()
        context_json = json.dumps(context) if context else None
        with self._lock:
            cur = self._conn.execute("SELECT success_count, failure_count FROM tool_outcomes WHERE name = ?", (name,))
            row = cur.fetchone()
            success_count = (row[0] if row else 0) + (1 if success else 0)
            failure_count = (row[1] if row else 0) + (0 if success else 1)
            total = success_count + failure_count
            confidence = success_count / total if total else 0.0
            self._conn.execute(
                """INSERT INTO tool_outcomes (name, success_count, failure_count, confidence, last_context, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     success_count = excluded.success_count,
                     failure_count = excluded.failure_count,
                     confidence = excluded.confidence,
                     last_context = excluded.last_context,
                     updated_at = excluded.updated_at""",
                (name, success_count, failure_count, confidence, context_json, now),
            )
            self._conn.commit()
        return {"name": name, "success_count": success_count, "failure_count": failure_count, "confidence": confidence}

    def get_tool_outcome(self, name: str) -> Optional[Dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT name, success_count, failure_count, confidence, last_context, updated_at "
                "FROM tool_outcomes WHERE name = ?",
                (name,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "name": row[0],
            "success_count": row[1],
            "failure_count": row[2],
            "confidence": row[3],
            "last_context": row[4],
            "updated_at": row[5],
        }

    def update_steps(self, skill_id: int, steps: List[Dict]) -> Optional[Dict]:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE learned_skills SET steps_json = ?, updated_at = ? WHERE skill_id = ?",
                (json.dumps(steps), now, skill_id),
            )
            self._conn.commit()
        return self.get_skill(skill_id)

    def set_status(self, skill_id: int, status: str) -> Optional[Dict]:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE learned_skills SET status = ?, updated_at = ? WHERE skill_id = ?",
                (status, now, skill_id),
            )
            self._conn.commit()
        return self.get_skill(skill_id)

    def delete_skill(self, skill_id: int) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM learned_skills WHERE skill_id = ?", (skill_id,))
            self._conn.commit()
        return {"success": True, "skill_id": skill_id}

    @staticmethod
    def _row_to_skill(row) -> Dict:
        (
            skill_id,
            name,
            description,
            steps_json,
            source,
            status,
            success_count,
            failure_count,
            confidence,
            created_at,
            updated_at,
        ) = row
        try:
            steps = json.loads(steps_json) if steps_json else []
        except Exception:
            steps = []
        return {
            "skill_id": skill_id,
            "name": name,
            "description": description,
            "steps": steps,
            "source": source,
            "status": status,
            "success_count": success_count,
            "failure_count": failure_count,
            "confidence": confidence,
            "created_at": created_at,
            "updated_at": updated_at,
        }


def get_skill_store() -> SkillStore:
    """Process-wide SkillStore singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SkillStore()
    return _instance
