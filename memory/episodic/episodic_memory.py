"""Episodic memory (task episodes)
================================
memory/episodic_memory.py (flat module, Phase 2x) already logs single
instantaneous events - "user asked me to close Chrome at 3pm" - as a
one-row diary. What that log can't answer is "did the thing Ultron was
*doing* actually work, and what steps did it take to get there" - that
needs a bounded unit with a start, an end, an outcome, and the steps
in between, not a flat stream of one-liners.

That bounded unit is an Episode here: start_episode() opens one with a
kind + goal, add_step() logs what happened along the way, end_episode()
closes it with success/failure + an outcome summary. This is the layer
learning/pattern_detector.py mines for repeating step-sequences (to
promote into memory/procedural/) and learning/failure_learner.py mines
for episodes that keep ending in failure.

Kept as its own module rather than folded into the flat
episodic_memory.py: that module's job is *what happened*
(instantaneous, tag-searchable); this one's job is *how a multi-step
attempt went* (bounded, outcome-scored). Both are legitimately
"episodic" in the cognitive-architecture sense; they just answer
different questions, same way memory/history/history.py (whole
sessions) and memory/history/tracker.py (per-interaction audit log)
split by granularity instead of superseding each other.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "episodic_task_memory.db"


class EpisodicMemory:
    """Bounded task episodes (start -> steps -> end), each with a success outcome."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT,
                goal TEXT,
                context TEXT,
                success INTEGER,
                outcome TEXT,
                started_at REAL,
                ended_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS episode_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER,
                description TEXT,
                success INTEGER,
                detail TEXT,
                occurred_at REAL
            )""")
        self._conn.commit()

    def start_episode(self, kind: str, goal: str, context: str = "") -> Dict:
        """Open a new episode. `kind` is a short free-form category
        ("file_organize", "web_search", "goal_execution", ...) - the same
        vocabulary callers use for their own tool/task names, so it lines
        up with memory/history/tracker.py's `name` field if a caller wants
        to cross-reference the two."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO episodes (kind, goal, context, success, outcome, started_at, ended_at) "
                "VALUES (?, ?, ?, NULL, NULL, ?, NULL)",
                (kind, goal, context, time.time()),
            )
            self._conn.commit()
            return {"success": True, "episode_id": cur.lastrowid, "kind": kind, "goal": goal}
        except Exception as e:
            return {"error": str(e)}

    def add_step(self, episode_id: int, description: str, success: bool = True, detail: Optional[Dict] = None) -> Dict:
        """Log one step within an in-progress episode."""
        try:
            self._conn.execute(
                "INSERT INTO episode_steps (episode_id, description, success, detail, occurred_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (episode_id, description, 1 if success else 0, json.dumps(detail or {}), time.time()),
            )
            self._conn.commit()
            return {"success": True, "episode_id": episode_id, "step": description}
        except Exception as e:
            return {"error": str(e)}

    def end_episode(self, episode_id: int, success: bool, outcome: str = "") -> Dict:
        """Close an episode with its final success/failure outcome."""
        try:
            cur = self._conn.execute(
                "UPDATE episodes SET success = ?, outcome = ?, ended_at = ? WHERE id = ?",
                (1 if success else 0, outcome, time.time(), episode_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No episode with id {episode_id}"}
            return {"success": True, "episode_id": episode_id, "outcome_success": success}
        except Exception as e:
            return {"error": str(e)}

    def get_episode(self, episode_id: int) -> Dict:
        """Full episode record plus its ordered steps."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT kind, goal, context, success, outcome, started_at, ended_at FROM episodes WHERE id = ?",
                (episode_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": f"No episode with id {episode_id}"}
            cur.execute(
                "SELECT description, success, detail, occurred_at FROM episode_steps "
                "WHERE episode_id = ? ORDER BY occurred_at",
                (episode_id,),
            )
            steps = [
                {"description": d, "success": bool(s), "detail": json.loads(det or "{}"), "occurred_at": ts}
                for d, s, det, ts in cur.fetchall()
            ]
            return {
                "episode_id": episode_id,
                "kind": row[0],
                "goal": row[1],
                "context": row[2],
                "success": bool(row[3]) if row[3] is not None else None,
                "outcome": row[4],
                "started_at": row[5],
                "ended_at": row[6],
                "steps": steps,
            }
        except Exception as e:
            return {"error": str(e)}

    def recent_episodes(self, limit: int = 20, kind: Optional[str] = None, success: Optional[bool] = None) -> Dict:
        """Most recently started episodes, newest first, optionally filtered."""
        try:
            clauses, params = [], []
            if kind is not None:
                clauses.append("kind = ?")
                params.append(kind)
            if success is not None:
                clauses.append("success = ?")
                params.append(1 if success else 0)
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            cur = self._conn.cursor()
            cur.execute(
                f"SELECT id, kind, goal, success, outcome, started_at, ended_at FROM episodes "
                f"{where} ORDER BY started_at DESC LIMIT ?",
                (*params, limit),
            )
            rows = cur.fetchall()
            episodes = [self._row_to_summary(r) for r in rows]
            return {"count": len(episodes), "episodes": episodes}
        except Exception as e:
            return {"error": str(e)}

    def episodes_between(self, start_ts: float, end_ts: float) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, kind, goal, success, outcome, started_at, ended_at FROM episodes "
                "WHERE started_at BETWEEN ? AND ? ORDER BY started_at",
                (start_ts, end_ts),
            )
            episodes = [self._row_to_summary(r) for r in cur.fetchall()]
            return {"count": len(episodes), "episodes": episodes}
        except Exception as e:
            return {"error": str(e)}

    def search_episodes(self, query: str, limit: int = 20) -> Dict:
        """Substring search over goal/context/outcome."""
        try:
            like = f"%{query}%"
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id, kind, goal, success, outcome, started_at, ended_at FROM episodes "
                "WHERE goal LIKE ? OR context LIKE ? OR outcome LIKE ? "
                "ORDER BY started_at DESC LIMIT ?",
                (like, like, like, limit),
            )
            episodes = [self._row_to_summary(r) for r in cur.fetchall()]
            return {"query": query, "count": len(episodes), "episodes": episodes}
        except Exception as e:
            return {"error": str(e)}

    def failure_rate_by_kind(self) -> Dict:
        """Success rate per episode `kind`, for callers (learning/failure_learner.py,
        learning/pattern_detector.py) that want to spot kinds that keep failing."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT kind, COUNT(*), SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) "
                "FROM episodes WHERE success IS NOT NULL GROUP BY kind"
            )
            out = {}
            for kind, total, successes in cur.fetchall():
                out[kind] = {
                    "attempts": total,
                    "successes": successes or 0,
                    "success_rate": round((successes or 0) / total, 3) if total else None,
                }
            return out
        except Exception as e:
            return {"error": str(e)}

    def _delete_episode(self, episode_id: int) -> bool:
        """Private on purpose, same convention as memory/forget.py's
        _delete_person/_delete_place/_delete_fact/_delete_action. The only
        intended caller is learning/forgetting.py, and only ever for an
        episode that learning/memory_consolidator.py has already folded
        into a memory/semantic/ pattern (see SemanticMemory.
        all_source_episode_ids()) - so the raw row can go without losing
        what was learned from it. Cascades to that episode's steps too."""
        try:
            cur = self._conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            self._conn.execute("DELETE FROM episode_steps WHERE episode_id = ?", (episode_id,))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception:
            return False

    @staticmethod
    def _row_to_summary(row) -> Dict:
        eid, kind, goal, success, outcome, started_at, ended_at = row
        return {
            "episode_id": eid,
            "kind": kind,
            "goal": goal,
            "success": bool(success) if success is not None else None,
            "outcome": outcome,
            "started_at": started_at,
            "ended_at": ended_at,
        }


_episodic_memory: Optional[EpisodicMemory] = None


def get_episodic_memory() -> EpisodicMemory:
    """Process-wide singleton, matching memory.long_term.get_long_term_memory()."""
    global _episodic_memory
    if _episodic_memory is None:
        _episodic_memory = EpisodicMemory()
    return _episodic_memory
