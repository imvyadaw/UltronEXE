"""
Skill Versions (Phase 30 - Skills)
=====================================
intelligence/skill_builder/skill_store.py's update_steps() overwrites
a skill's steps in place - there is no history, so a skill_improver.py
change that makes things worse can't be told apart from the original,
and can't be undone. This module adds that missing version history as
a thin layer on top of skill_store: every update_steps-equivalent call
here snapshots the previous version before writing the new one, and
revert() restores an older snapshot as the new current version (never
deletes history, so revert itself is also just another version).

Storage: database/skill_versions.db, table skill_versions - separate
file from skill_store's own database/skill_builder.db so this stays
purely additive and skill_store.py needs no changes to keep working
exactly as it does today for callers that don't care about history.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("ultron.skills.versions")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "skill_versions.db"


class SkillVersions:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    steps TEXT NOT NULL,
                    note TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.commit()

    def _next_version(self, conn: sqlite3.Connection, skill_id: int) -> int:
        row = conn.execute("SELECT MAX(version) FROM skill_versions WHERE skill_id = ?", (skill_id,)).fetchone()
        return (row[0] or 0) + 1

    def snapshot(self, skill_id: int, steps: List[Dict], note: str = "") -> int:
        """Record `steps` as the new current version for skill_id.
        Callers updating a skill's steps should call this *instead of*
        (or immediately alongside) skill_store.update_steps(), passing
        the same new steps, so history stays in sync with what's live."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            version = self._next_version(conn, skill_id)
            conn.execute(
                "INSERT INTO skill_versions (skill_id, version, steps, note, created_at) " "VALUES (?, ?, ?, ?, ?)",
                (skill_id, version, json.dumps(steps), note, time.time()),
            )
            conn.commit()
            logger.info(f"Skill {skill_id} snapshotted as v{version} ({note or 'no note'})")
            return version

    def history(self, skill_id: int) -> List[Dict]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT version, note, created_at FROM skill_versions " "WHERE skill_id = ? ORDER BY version DESC",
                (skill_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_version(self, skill_id: int, version: int) -> Optional[List[Dict]]:
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT steps FROM skill_versions WHERE skill_id = ? AND version = ?", (skill_id, version)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def revert(self, skill_id: int, to_version: int) -> Optional[int]:
        """Restores an older version's steps as the current live steps
        (via skill_store.update_steps) and records the revert itself
        as a brand new version, so the history line never goes
        backwards - it just gains a new entry that happens to match an
        older one."""
        steps = self.get_version(skill_id, to_version)
        if steps is None:
            return None
        try:
            from intelligence.skill_builder.skill_store import get_skill_store

            get_skill_store().update_steps(skill_id, steps)
        except Exception as e:
            logger.error(f"Could not apply reverted steps to skill_store: {e}")
            return None
        return self.snapshot(skill_id, steps, note=f"reverted to v{to_version}")


_instance: Optional[SkillVersions] = None
_instance_lock = threading.Lock()


def get_skill_versions() -> SkillVersions:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SkillVersions()
    return _instance
