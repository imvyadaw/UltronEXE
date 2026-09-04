"""
Verification Engine (Phase 19.4 - Verification)
===================================================
Single entry point for the verification/ package: run a named
verification (a list of checks, evaluated through
success_evaluator.py), and persist the outcome so verification
history is queryable afterwards - "did this actually work" shouldn't
only live in memory for the one caller that asked at the time.
action_verifier.py's action-shaped checks and success_evaluator.py's
generic checks can both be run through here.

Storage: database/verification.db, table verification_runs (this
module's own table; screenshot_verifier.py keeps its baselines in
the same database file under a different table).
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.verification.action_verifier import get_action_verifier
from intelligence.verification.success_evaluator import get_success_evaluator

logger = get_logger("ultron.verification_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "verification.db"

_instance: Optional["VerificationEngine"] = None
_instance_lock = threading.Lock()


class VerificationEngine:
    """Runs verifications through success_evaluator/action_verifier and
    logs every run to database/verification.db so results can be
    looked back on."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS verification_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                passed INTEGER,
                score REAL,
                checks_json TEXT,
                results_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._evaluator = get_success_evaluator()
        self._action_verifier = get_action_verifier()

    # -- core verification ------------------------------------------------------
    def verify(self, label: str, checks: List[Dict], require_all: bool = True, pass_threshold: float = 1.0) -> Dict:
        """Run a list of success_evaluator-shaped checks under a given
        label (e.g. a goal id, a task name), log the run, return the
        evaluation plus its run_id."""
        outcome = self._evaluator.evaluate(checks, require_all=require_all, pass_threshold=pass_threshold)
        run_id = self._log_run(label, outcome, checks)
        if outcome.get("passed") is False:
            logger.info(f"verification '{label}' FAILED - score {outcome.get('score')}")
        elif outcome.get("passed") is True:
            logger.info(f"verification '{label}' passed - score {outcome.get('score')}")
        return {"run_id": run_id, "label": label, **outcome}

    def verify_action(self, action_name: str, checks: Optional[Dict] = None) -> Dict:
        """Convenience passthrough to action_verifier.py for the
        action-shaped (expect_file / expect_screenshot_changed / ...)
        check format, also logged to verification_runs."""
        outcome = self._action_verifier.verify_action(action_name, checks)
        run_id = self._log_run(
            action_name,
            {
                "passed": outcome["passed"],
                "score": 1.0 if outcome["passed"] else 0.0,
                "results": outcome["checks"],
            },
            checks or {},
        )
        return {"run_id": run_id, **outcome}

    def _log_run(self, label: str, outcome: Dict, checks) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO verification_runs (label, passed, score, checks_json, results_json, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    label,
                    int(bool(outcome.get("passed"))),
                    outcome.get("score", 0.0),
                    json.dumps(checks, default=str),
                    json.dumps(outcome.get("results", []), default=str),
                    now,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    # -- history ------------------------------------------------------------------
    def get_run(self, run_id: int) -> Dict:
        with self._lock:
            cur = self._conn.execute(
                """SELECT id, label, passed, score, checks_json, results_json, timestamp
                   FROM verification_runs WHERE id = ?""",
                (run_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"error": f"no run with id {run_id}"}
        return self._row_to_dict(row)

    def get_history(self, label: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if label:
                cur = self._conn.execute(
                    """SELECT id, label, passed, score, checks_json, results_json, timestamp
                       FROM verification_runs WHERE label = ? ORDER BY id DESC LIMIT ?""",
                    (label, limit),
                )
            else:
                cur = self._conn.execute(
                    """SELECT id, label, passed, score, checks_json, results_json, timestamp
                       FROM verification_runs ORDER BY id DESC LIMIT ?""",
                    (limit,),
                )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> Dict:
        try:
            checks = json.loads(row[4]) if row[4] else []
        except Exception:
            checks = []
        try:
            results = json.loads(row[5]) if row[5] else []
        except Exception:
            results = []
        return {
            "id": row[0],
            "label": row[1],
            "passed": bool(row[2]),
            "score": row[3],
            "checks": checks,
            "results": results,
            "timestamp": row[6],
        }


def get_verification_engine() -> VerificationEngine:
    """Process-wide VerificationEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = VerificationEngine()
    return _instance
