"""
Self Critique (Phase 23.5 - Cognitive Reasoning Layer)
=========================================================
Fifth stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). After a response has been
produced or a decided-on step has run, this module asks the LLM to
critique that output against the original goal: what's good about it,
what's weak or risky about it, and - if it's clearly flawed - a
concrete revision. verification_engine.py (next stage) then checks
the critique's factual/logical claims; this module is the "does this
look right" pass, verification_engine.py is the "is this actually
right" pass.

Goes through ai.ai_router like every other LLM call in this layer, so
it inherits the same online/offline fallback. If the LLM path is
unavailable, critique() falls back to a small set of cheap structural
checks (empty output, error strings, suspiciously short output for a
complex goal) rather than skipping review entirely.

Storage: database/self_critique.db, table critiques.
"""

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.self_critique")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.self_critique")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router
except Exception as exc:  # pragma: no cover
    get_router = None
    logger.warning(f"[self_critique] ai.ai_router unavailable, using structural checks only: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "self_critique.db"

_instance: Optional["SelfCritique"] = None
_instance_lock = threading.Lock()

CRITIQUE_PROMPT = """You are reviewing your own work before it's shown to the user.
Goal: {goal}
Output produced: {output}

Respond with ONLY a JSON object, nothing else - no prose, no markdown fences:
{{
  "quality_score": 0.0-1.0,
  "strengths": ["short points"],
  "weaknesses": ["short points, empty list if none"],
  "flawed": true/false,
  "revision_suggestion": "only if flawed is true, else empty string"
}}"""

_ERROR_MARKERS = ("error:", "exception", "traceback", "failed to", "could not")


class SelfCritique:
    """critique(goal, output) -> quality assessment + optional revision suggestion."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS critiques (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT,
                output TEXT,
                quality_score REAL,
                flawed INTEGER,
                result_json TEXT,
                source TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

    def critique(self, goal: str, output: str) -> Dict:
        """Review `output` against `goal`. Always returns a usable
        result - falls back to structural checks if the LLM path is
        unavailable or fails."""
        goal = (goal or "").strip()
        output = (output or "").strip()
        if not output:
            result = {
                "quality_score": 0.0,
                "strengths": [],
                "weaknesses": ["output is empty"],
                "flawed": True,
                "revision_suggestion": "produce a non-empty response",
            }
            self._log(goal, output, result, "structural")
            return result

        result = self._critique_with_llm(goal, output) if get_router is not None else None
        source = "llm"
        if result is None:
            result = self._critique_structural(goal, output)
            source = "structural"

        self._log(goal, output, result, source)
        if result.get("flawed"):
            logger.info(
                f"[self_critique] flagged output for goal '{goal[:60]}' as flawed "
                f"(score={result.get('quality_score')})"
            )
        return result

    def _critique_with_llm(self, goal: str, output: str) -> Optional[Dict]:
        try:
            prompt = CRITIQUE_PROMPT.format(goal=goal or "(no explicit goal given)", output=output[:1500])
            raw = get_router().complete(prompt, temperature=0.2, max_tokens=400)
            text = raw.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return None
            score = parsed.get("quality_score")
            try:
                score = max(0.0, min(1.0, float(score)))
            except (TypeError, ValueError):
                score = 0.5
            return {
                "quality_score": score,
                "strengths": list(parsed.get("strengths") or []),
                "weaknesses": list(parsed.get("weaknesses") or []),
                "flawed": bool(parsed.get("flawed", score < 0.5)),
                "revision_suggestion": str(parsed.get("revision_suggestion", "")),
            }
        except Exception as e:
            logger.info(f"[self_critique] LLM critique failed, falling back to structural checks: {e}")
            return None

    @staticmethod
    def _critique_structural(goal: str, output: str) -> Dict:
        lowered = output.lower()
        weaknesses = []
        if any(marker in lowered for marker in _ERROR_MARKERS):
            weaknesses.append("output contains an error/exception marker")
        if goal and len(output.split()) < 3 and len(goal.split()) > 8:
            weaknesses.append("output looks too short for how involved the goal was")

        flawed = bool(weaknesses)
        return {
            "quality_score": 0.3 if flawed else 0.7,
            "strengths": [] if flawed else ["no obvious structural problems found"],
            "weaknesses": weaknesses,
            "flawed": flawed,
            "revision_suggestion": "review and retry" if flawed else "",
        }

    def _log(self, goal: str, output: str, result: Dict, source: str) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO critiques (goal, output, quality_score, flawed, result_json, source, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    goal,
                    output[:2000],
                    result.get("quality_score", 0.0),
                    int(bool(result.get("flawed"))),
                    json.dumps(result, default=str),
                    source,
                    now,
                ),
            )
            self._conn.commit()

    def recent(self, limit: int = 20, flawed_only: bool = False) -> List[Dict]:
        with self._lock:
            if flawed_only:
                rows = self._conn.execute(
                    """SELECT goal, output, quality_score, flawed, result_json, source, timestamp
                       FROM critiques WHERE flawed = 1 ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT goal, output, quality_score, flawed, result_json, source, timestamp
                       FROM critiques ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        out = []
        for goal, output, score, flawed, result_json, source, ts in rows:
            try:
                result = json.loads(result_json)
            except Exception:
                result = {}
            out.append(
                {
                    "goal": goal,
                    "output": output,
                    "quality_score": score,
                    "flawed": bool(flawed),
                    "result": result,
                    "source": source,
                    "timestamp": ts,
                }
            )
        return out


def get_self_critique() -> SelfCritique:
    """Process-wide SelfCritique singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SelfCritique()
    return _instance
