"""Semantic memory (generalized patterns)
=======================================
memory/semantic_memory.py (flat module, Phase 2x) already stores
encyclopedic concept definitions and typed relations between them -
"a VPN encrypts network traffic", "Alex is the user's manager". That's
knowledge Ultron was *told* or looked up. This module stores a
different kind of "general, timeless" knowledge: regularities Ultron
*noticed itself* by generalizing across many specific episodes -
"the user usually starts a 'deploy' episode around 6pm", "'clear
cache' episodes fail about a third of the time". Those aren't facts
about the world; they're patterns about how things around here tend to
go, discovered rather than stated.

learning/pattern_detector.py is the only intended writer of new
patterns (via add_pattern()/reinforce_pattern()); this module is just
the storage + confidence bookkeeping. A pattern's confidence starts
low and only rises when the same regularity is observed again
(reinforce_pattern()) - a single episode is never enough to call
something a pattern.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "semantic_pattern_memory.db"

DEFAULT_CONFIDENCE = 0.4
REINFORCE_STEP = 0.08
MAX_CONFIDENCE = 0.97


class SemanticMemory:
    """Generalized behavioral patterns distilled from episodic memory, each with a confidence score."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT,
                description TEXT,
                trigger_condition TEXT,
                typical_outcome TEXT,
                confidence REAL,
                observation_count INTEGER,
                source_episode_ids TEXT,
                created_at REAL,
                updated_at REAL
            )""")
        self._conn.commit()

    def add_pattern(
        self,
        pattern_type: str,
        description: str,
        trigger_condition: str = "",
        typical_outcome: str = "",
        confidence: float = DEFAULT_CONFIDENCE,
        source_episode_ids: Optional[List[int]] = None,
    ) -> Dict:
        """Store a newly-detected pattern, or reinforce it if an
        equivalent one (same type + description) already exists rather
        than creating a duplicate row."""
        try:
            existing = self._find_by_description(pattern_type, description)
            if existing:
                return self.reinforce_pattern(existing["id"], source_episode_ids=source_episode_ids)
            now = time.time()
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO patterns (pattern_type, description, trigger_condition, typical_outcome, "
                "confidence, observation_count, source_episode_ids, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)",
                (
                    pattern_type,
                    description,
                    trigger_condition,
                    typical_outcome,
                    min(confidence, MAX_CONFIDENCE),
                    json.dumps(source_episode_ids or []),
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return {"success": True, "pattern_id": cur.lastrowid, "confidence": confidence, "new": True}
        except Exception as e:
            return {"error": str(e)}

    def reinforce_pattern(self, pattern_id: int, source_episode_ids: Optional[List[int]] = None) -> Dict:
        """A pattern was observed again - bump its confidence and
        observation count instead of adding a duplicate row."""
        try:
            pattern = self.get_pattern(pattern_id)
            if "error" in pattern:
                return pattern
            new_confidence = min(pattern["confidence"] + REINFORCE_STEP, MAX_CONFIDENCE)
            ids = set(pattern.get("source_episode_ids", [])) | set(source_episode_ids or [])
            self._conn.execute(
                "UPDATE patterns SET confidence = ?, observation_count = observation_count + 1, "
                "source_episode_ids = ?, updated_at = ? WHERE id = ?",
                (new_confidence, json.dumps(sorted(ids)), time.time(), pattern_id),
            )
            self._conn.commit()
            return {"success": True, "pattern_id": pattern_id, "confidence": new_confidence, "new": False}
        except Exception as e:
            return {"error": str(e)}

    def get_pattern(self, pattern_id: int) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT pattern_type, description, trigger_condition, typical_outcome, confidence, "
                "observation_count, source_episode_ids, created_at, updated_at FROM patterns WHERE id = ?",
                (pattern_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": f"No pattern with id {pattern_id}"}
            return self._row_to_dict((pattern_id, *row))
        except Exception as e:
            return {"error": str(e)}

    def get_patterns(self, pattern_type: Optional[str] = None, min_confidence: float = 0.0) -> Dict:
        try:
            cur = self._conn.cursor()
            if pattern_type:
                cur.execute(
                    "SELECT id, pattern_type, description, trigger_condition, typical_outcome, confidence, "
                    "observation_count, source_episode_ids, created_at, updated_at FROM patterns "
                    "WHERE pattern_type = ? AND confidence >= ? ORDER BY confidence DESC",
                    (pattern_type, min_confidence),
                )
            else:
                cur.execute(
                    "SELECT id, pattern_type, description, trigger_condition, typical_outcome, confidence, "
                    "observation_count, source_episode_ids, created_at, updated_at FROM patterns "
                    "WHERE confidence >= ? ORDER BY confidence DESC",
                    (min_confidence,),
                )
            patterns = [self._row_to_dict(r) for r in cur.fetchall()]
            return {"count": len(patterns), "patterns": patterns}
        except Exception as e:
            return {"error": str(e)}

    def search_patterns(self, query: str) -> Dict:
        try:
            like = f"%{query}%"
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, pattern_type, description, trigger_condition, typical_outcome, confidence, "
                "observation_count, source_episode_ids, created_at, updated_at FROM patterns "
                "WHERE description LIKE ? OR trigger_condition LIKE ? ORDER BY confidence DESC",
                (like, like),
            )
            patterns = [self._row_to_dict(r) for r in cur.fetchall()]
            return {"query": query, "count": len(patterns), "patterns": patterns}
        except Exception as e:
            return {"error": str(e)}

    def all_source_episode_ids(self) -> set:
        """Every episode id referenced by any pattern's source_episode_ids -
        used by learning/memory_consolidator.py (has this episode already
        been folded into a regularity?) and learning/forgetting.py (is it
        therefore safe to prune the raw episode row?)."""
        try:
            ids: set = set()
            cur = self._conn.cursor()
            cur.execute("SELECT source_episode_ids FROM patterns")
            for (raw,) in cur.fetchall():
                try:
                    ids.update(json.loads(raw or "[]"))
                except json.JSONDecodeError:
                    continue
            return ids
        except Exception:
            return set()

    def _delete_pattern(self, pattern_id: int) -> bool:
        """Private on purpose, same convention as memory/forget.py's
        _delete_person/_delete_place/_delete_fact/_delete_action - the only
        intended caller is learning/forgetting.py, which logs every prune to
        its own audit trail (storage/learning/forgetting_log.json) before
        calling this. Nothing else in memory/semantic/ or learning/
        pattern_detector.py deletes a pattern - see this module's docstring."""
        try:
            cur = self._conn.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception:
            return False

    def _find_by_description(self, pattern_type: str, description: str) -> Optional[Dict]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT id FROM patterns WHERE pattern_type = ? AND description = ?",
            (pattern_type, description),
        )
        row = cur.fetchone()
        return {"id": row[0]} if row else None

    @staticmethod
    def _row_to_dict(row) -> Dict:
        pid, ptype, desc, trigger, outcome, confidence, obs_count, source_ids, created_at, updated_at = row
        try:
            source_ids = json.loads(source_ids or "[]")
        except json.JSONDecodeError:
            source_ids = []
        return {
            "id": pid,
            "pattern_type": ptype,
            "description": desc,
            "trigger_condition": trigger,
            "typical_outcome": outcome,
            "confidence": confidence,
            "observation_count": obs_count,
            "source_episode_ids": source_ids,
            "created_at": created_at,
            "updated_at": updated_at,
        }


_semantic_memory: Optional[SemanticMemory] = None


def get_semantic_pattern_memory() -> SemanticMemory:
    """Process-wide singleton. Named `..._pattern_memory` rather than
    reusing `get_semantic_memory` since memory/semantic_memory.py's flat
    module already exports a same-named concept for a different store -
    see this module's docstring for the split."""
    global _semantic_memory
    if _semantic_memory is None:
        _semantic_memory = SemanticMemory()
    return _semantic_memory
