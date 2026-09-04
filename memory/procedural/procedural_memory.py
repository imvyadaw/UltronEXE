"""Procedural memory (outcome-tracked procedures)
================================================
memory/procedural_memory.py (flat module, Phase 2x) already saves
named step-sequences with a `times_used` counter - good enough for
"which procedures get reused most". What it can't answer is "which
saved procedures actually *work*", because it only counts usage, not
outcome. That's the gap this module fills: record_outcome() splits
usage into success_count/failure_count, so every saved procedure has a
real success_rate, and learning/failure_learner.py has something to
flag when it drops too low.

Same step shape as the flat module ({"tool": ..., "arguments": {...}},
ready for core/executor.py / core/workflow_engine.py to replay), so a
procedure learned/promoted here is a drop-in replacement for one saved
there - this module just tracks whether replaying it was worth it.
learning/pattern_detector.py is the intended source of *new*
procedures here (promoting a step-sequence it saw repeat across
several successful episodes); anything already hand-saved via the flat
module is untouched and keeps working independently.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[2] / "storage" / "sqlite" / "procedural_outcome_memory.db"


class ProceduralMemory:
    """Named step-sequences with success/failure outcome tracking."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS procedures (
                name TEXT PRIMARY KEY,
                description TEXT,
                steps TEXT,
                goal_keywords TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                created_at REAL,
                last_used_at REAL
            )""")
        self._conn.commit()

    def save_procedure(self, name: str, steps: List[Dict], description: str = "", goal_keywords: str = "") -> Dict:
        """Save (or overwrite the definition of) a named procedure.
        Overwriting keeps the existing success/failure counts - a
        procedure's steps can be corrected without losing its track
        record."""
        try:
            existing = self.get_procedure(name)
            success_count = existing.get("success_count", 0) if "error" not in existing else 0
            failure_count = existing.get("failure_count", 0) if "error" not in existing else 0
            self._conn.execute(
                "INSERT INTO procedures (name, description, steps, goal_keywords, success_count, "
                "failure_count, created_at, last_used_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL) "
                "ON CONFLICT(name) DO UPDATE SET description = excluded.description, "
                "steps = excluded.steps, goal_keywords = excluded.goal_keywords",
                (name, description, json.dumps(steps), goal_keywords, success_count, failure_count, time.time()),
            )
            self._conn.commit()
            return {"success": True, "name": name, "step_count": len(steps)}
        except Exception as e:
            return {"error": str(e)}

    def record_outcome(self, name: str, success: bool) -> Dict:
        """Call each time a procedure is replayed, with whether it worked."""
        try:
            column = "success_count" if success else "failure_count"
            cur = self._conn.execute(
                f"UPDATE procedures SET {column} = {column} + 1, last_used_at = ? WHERE name = ?",
                (time.time(), name),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No procedure named '{name}'"}
            return {"success": True, "name": name, **self._success_rate(name)}
        except Exception as e:
            return {"error": str(e)}

    def get_procedure(self, name: str) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT description, steps, goal_keywords, success_count, failure_count, "
                "created_at, last_used_at FROM procedures WHERE name = ?",
                (name,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": f"No procedure named '{name}'"}
            return self._row_to_dict(name, row)
        except Exception as e:
            return {"error": str(e)}

    def list_procedures(self, min_success_rate: Optional[float] = None) -> Dict:
        """All saved procedures with computed success_rate, most-used first.
        `min_success_rate` filters out anything below that rate (procedures
        never used yet are always included - no track record isn't a bad one)."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT name, description, steps, goal_keywords, success_count, failure_count, "
                "created_at, last_used_at FROM procedures "
                "ORDER BY (success_count + failure_count) DESC"
            )
            procedures = [self._row_to_dict(r[0], r[1:]) for r in cur.fetchall()]
            if min_success_rate is not None:
                procedures = [
                    p for p in procedures if p["success_rate"] is None or p["success_rate"] >= min_success_rate
                ]
            return {"count": len(procedures), "procedures": procedures}
        except Exception as e:
            return {"error": str(e)}

    def best_procedure_for(self, goal_text: str) -> Dict:
        """Best-matching saved procedure for a goal, ranked by keyword
        overlap first and success_rate as the tiebreaker - a cheap
        substring-based retrieval, not semantic search (see
        ai/embeddings.py / memory/vector_db for that if it's ever needed
        here)."""
        try:
            words = set(goal_text.lower().split())
            all_procs = self.list_procedures()["procedures"]
            scored = []
            for proc in all_procs:
                keywords = set(proc.get("goal_keywords", "").lower().split(",")) - {""}
                keywords |= set(proc["name"].lower().replace("_", " ").split())
                overlap = len(words & keywords)
                if overlap > 0:
                    scored.append((overlap, proc.get("success_rate") or 0.5, proc))
            if not scored:
                return {"found": False, "goal": goal_text}
            scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
            return {"found": True, "goal": goal_text, "procedure": scored[0][2]}
        except Exception as e:
            return {"error": str(e)}

    def flag_unreliable(self, threshold: float = 0.4, min_uses: int = 3) -> Dict:
        """Procedures with at least `min_uses` attempts and a success_rate
        below `threshold` - what learning/failure_learner.py checks
        before letting Ultron reach for a saved procedure unprompted."""
        try:
            flagged = [
                p
                for p in self.list_procedures()["procedures"]
                if (p["success_count"] + p["failure_count"]) >= min_uses
                and p["success_rate"] is not None
                and p["success_rate"] < threshold
            ]
            return {"count": len(flagged), "procedures": flagged}
        except Exception as e:
            return {"error": str(e)}

    def delete_procedure(self, name: str) -> Dict:
        try:
            cur = self._conn.execute("DELETE FROM procedures WHERE name = ?", (name,))
            self._conn.commit()
            if cur.rowcount == 0:
                return {"error": f"No procedure named '{name}'"}
            return {"success": True, "deleted": name}
        except Exception as e:
            return {"error": str(e)}

    def _success_rate(self, name: str) -> Dict:
        proc = self.get_procedure(name)
        return {"success_rate": proc.get("success_rate")} if "error" not in proc else {"success_rate": None}

    @staticmethod
    def _row_to_dict(name: str, row) -> Dict:
        description, steps, goal_keywords, success_count, failure_count, created_at, last_used_at = row
        total = (success_count or 0) + (failure_count or 0)
        return {
            "name": name,
            "description": description,
            "steps": json.loads(steps),
            "goal_keywords": goal_keywords,
            "success_count": success_count or 0,
            "failure_count": failure_count or 0,
            "success_rate": round((success_count or 0) / total, 3) if total else None,
            "created_at": created_at,
            "last_used_at": last_used_at,
        }


_procedural_memory: Optional[ProceduralMemory] = None


def get_procedural_outcome_memory() -> ProceduralMemory:
    """Process-wide singleton. Named `..._outcome_memory` rather than
    reusing `get_procedural_memory` since memory/procedural_memory.py's
    flat module already exports that name for the usage-count-only store -
    see this module's docstring for the split."""
    global _procedural_memory
    if _procedural_memory is None:
        _procedural_memory = ProceduralMemory()
    return _procedural_memory
