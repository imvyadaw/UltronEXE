"""
Workflow Detector (Phase 19.6 - Skill Builder)
==================================================
Mines the general action history workflow_recorder.py keeps (not
explicit recordings - the ambient stream of everything ULTRON does)
for contiguous sequences of actions that keep repeating on their
own. A user doing "open_file -> edit_file -> save_file" three
separate times without ever pressing "record" is exactly the pattern
this exists to catch, since that repetition is itself evidence the
sequence is worth turning into a skill.

Detection is a simple sliding-window n-gram count over action names
only (params are ignored here - workflow_analyzer.py is what figures
out which params are constant vs variable once a pattern is picked
as a candidate). Counts persist across restarts so a pattern seen
twice yesterday and once today still crosses the threshold today.
Deliberately simple/heuristic, same spirit as Phase 19.5's
regex-based failure classification - scanning the same recent window
more than once will recount overlapping occurrences, which is fine
for "is this worth suggesting as a skill" but not a precise count.

Storage: database/learned_skills.db, table detected_patterns.
"""

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "learned_skills.db"

_instance: Optional["WorkflowDetector"] = None
_instance_lock = threading.Lock()


class WorkflowDetector:
    """Sliding-window n-gram scan over an action-name sequence, with
    occurrence counts persisted per pattern signature."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS detected_patterns (
                signature TEXT PRIMARY KEY,
                actions_json TEXT,
                occurrence_count INTEGER DEFAULT 0,
                first_seen_at REAL,
                last_seen_at REAL
            )""")
        self._conn.commit()

    def scan(self, steps: List[Dict], min_len: int = 2, max_len: int = 6) -> List[Dict]:
        """Count every contiguous action-name n-gram (min_len..max_len)
        found in `steps` (as from workflow_recorder.get_recent_actions()),
        add those counts to the persisted totals, and return the
        updated stats for every pattern touched by this scan."""
        names = [s["action_name"] for s in steps]
        counts: Dict[tuple, int] = {}
        for n in range(min_len, max_len + 1):
            for i in range(len(names) - n + 1):
                gram = tuple(names[i : i + n])
                counts[gram] = counts.get(gram, 0) + 1

        if not counts:
            return []

        now = time.time()
        with self._lock:
            for gram, count in counts.items():
                signature = self._signature(gram)
                self._conn.execute(
                    """INSERT INTO detected_patterns
                       (signature, actions_json, occurrence_count, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(signature) DO UPDATE SET
                           occurrence_count = occurrence_count + excluded.occurrence_count,
                           last_seen_at = excluded.last_seen_at""",
                    (signature, json.dumps(list(gram)), count, now, now),
                )
            self._conn.commit()

            touched = []
            for gram in counts:
                signature = self._signature(gram)
                cur = self._conn.execute(
                    """SELECT signature, actions_json, occurrence_count, first_seen_at, last_seen_at
                       FROM detected_patterns WHERE signature = ?""",
                    (signature,),
                )
                row = cur.fetchone()
                if row:
                    touched.append(self._row_to_pattern(row))
        return touched

    def get_candidates(self, min_occurrences: int = 3, limit: int = 10) -> List[Dict]:
        """Persisted patterns that have crossed the repetition
        threshold, most-repeated first. Occurrence count is the
        stronger signal than raw length: a 3-step pattern seen 4 times
        is better evidence of a real habit than a 6-step "pattern"
        that only cleared the threshold because it's that same 3-step
        cycle counted twice over - length only breaks ties between
        equally-well-evidenced candidates."""
        with self._lock:
            cur = self._conn.execute(
                """SELECT signature, actions_json, occurrence_count, first_seen_at, last_seen_at
                   FROM detected_patterns WHERE occurrence_count >= ?
                   ORDER BY occurrence_count DESC LIMIT ?""",
                (min_occurrences, limit * 3),
            )
            rows = cur.fetchall()
        patterns = [self._row_to_pattern(r) for r in rows]
        patterns.sort(key=lambda p: (p["occurrence_count"], len(p["actions"])), reverse=True)
        return patterns[:limit]

    def forget(self, signature: str) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM detected_patterns WHERE signature = ?", (signature,))
            self._conn.commit()
        return {"success": True, "signature": signature}

    @staticmethod
    def _signature(gram: tuple) -> str:
        raw = "|".join(gram)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _row_to_pattern(row) -> Dict:
        signature, actions_json, occurrence_count, first_seen_at, last_seen_at = row
        try:
            actions = json.loads(actions_json) if actions_json else []
        except Exception:
            actions = []
        return {
            "signature": signature,
            "actions": actions,
            "occurrence_count": occurrence_count,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
        }


def get_workflow_detector() -> WorkflowDetector:
    """Process-wide WorkflowDetector singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WorkflowDetector()
    return _instance


def run_unified_pattern_scan(
    steps: Optional[List[Dict]] = None,
    min_len: int = 2,
    max_len: int = 6,
    min_occurrences: int = 3,
    episode_lookback: int = 200,
) -> Dict:
    """Single entry point that runs both of this project's pattern
    detectors together, since - per this module's own docstring - they're
    complementary, not competing: this module answers "is this worth
    automating" over the raw action-name stream, while
    learning/pattern_detector.py answers "is this worth remembering as a
    regularity" over memory/episodic/'s bounded, outcome-scored episodes.
    Calling both from one place means a caller doing periodic maintenance
    (e.g. skill_builder_engine.py's detect_from_history(), or a scheduler)
    doesn't have to know both exist separately.

    `steps` is the ambient action-name stream this module's own scan()
    already expects (as from workflow_recorder.get_recent_actions()); if
    omitted, only learning/pattern_detector.py's episode-based detection
    runs. Never raises - either half degrading to an error dict just means
    the other half's results still come back.
    """
    result: Dict = {"workflow_candidates": None, "episodic_patterns": None}
    try:
        detector = get_workflow_detector()
        if steps is not None:
            detector.scan(steps, min_len=min_len, max_len=max_len)
        result["workflow_candidates"] = detector.get_candidates(min_occurrences=min_occurrences)
    except Exception as e:
        result["workflow_candidates"] = {"error": str(e)}

    try:
        from learning.pattern_detector import get_pattern_detector

        result["episodic_patterns"] = get_pattern_detector().run_detection(lookback=episode_lookback)
    except Exception as e:
        result["episodic_patterns"] = {"error": str(e)}

    return result
