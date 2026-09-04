"""
Reasoning Engine (Phase 23.2 - Cognitive Reasoning Layer)
=========================================================
Second stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). Takes intent_analyzer.py's
output (or a bare goal string) and picks the right depth of reasoning
for it:

    complexity == "simple"            -> skip reasoning, pass straight
                                          through (not worth the LLM call)
    complexity == "moderate"          -> ai/reasoning.py's single-shot
                                          chain-of-thought pass
    complexity == "complex"           -> ai/chain_of_thought.py's
                                          decompose -> answer each ->
                                          synthesize pipeline

Does NOT reimplement either reasoning strategy - both already exist
and are tuned (see their own headers); this module just decides which
one a given request deserves and records the trace either way, so
goal_planner.py/decision_engine.py downstream always have *some*
reasoning trace to point back to even for "simple" requests (a
single-line pass-through trace rather than nothing).

Storage: database/reasoning_engine.db, table reasoning_traces.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.reasoning_engine")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.reasoning_engine")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.reasoning import ReasoningEngine as _SingleShotReasoner
except Exception as exc:  # pragma: no cover
    _SingleShotReasoner = None
    logger.warning(f"[reasoning_engine] ai.reasoning unavailable: {exc}")

try:
    from ai.chain_of_thought import ChainOfThought as _MultiPassReasoner
except Exception as exc:  # pragma: no cover
    _MultiPassReasoner = None
    logger.warning(f"[reasoning_engine] ai.chain_of_thought unavailable: {exc}")

try:
    from intelligence.deliberative_reasoning import DeliberativeReasoner as _DeliberativeReasoner
except Exception as exc:  # pragma: no cover
    _DeliberativeReasoner = None
    logger.warning(f"[reasoning_engine] intelligence.deliberative_reasoning unavailable: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "reasoning_engine.db"

_instance: Optional["CognitiveReasoningEngine"] = None
_instance_lock = threading.Lock()

DEPTH_NONE = "pass_through"
DEPTH_SINGLE = "single_pass"
DEPTH_MULTI = "multi_pass"
DEPTH_DELIBERATIVE = "deliberative"


class CognitiveReasoningEngine:
    """reason(goal, complexity_hint) -> {"depth", "conclusion", "trace"}."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS reasoning_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT,
                depth TEXT,
                conclusion TEXT,
                trace_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._single = _SingleShotReasoner() if _SingleShotReasoner else None
        self._multi = _MultiPassReasoner() if _MultiPassReasoner else None
        try:
            self._deliberative = _DeliberativeReasoner() if _DeliberativeReasoner else None
        except Exception as e:  # e.g. ai_router import chain failed at construction time
            logger.warning(f"[reasoning_engine] deliberative reasoner unavailable: {e}")
            self._deliberative = None

    def reason(self, goal: str, complexity_hint: Optional[str] = None) -> Dict:
        """Reason about `goal` at a depth chosen from `complexity_hint`
        ("simple"/"moderate"/"complex", typically intent_analyzer.py's
        output) - defaults to "moderate" (a single reasoning pass) when
        no hint is given, since that's a safe middle ground for a caller
        that hasn't run intent analysis first."""
        goal = (goal or "").strip()
        if not goal:
            return {"error": "empty goal"}

        depth, result = self._reason_at_depth(goal, complexity_hint or "moderate")
        self._log_trace(goal, depth, result)
        return result

    def _reason_at_depth(self, goal: str, complexity: str) -> (str, Dict):
        if complexity == "simple":
            return DEPTH_NONE, {
                "depth": DEPTH_NONE,
                "goal": goal,
                "conclusion": goal,
                "trace": ["passed straight through - request judged simple enough to skip reasoning"],
            }

        if complexity == "complex" and self._deliberative is not None:
            try:
                outcome = self._deliberative.run(goal)
                if "error" not in outcome:
                    return DEPTH_DELIBERATIVE, {
                        "depth": DEPTH_DELIBERATIVE,
                        "goal": goal,
                        "conclusion": outcome.get("final_answer", ""),
                        "confidence": outcome.get("confidence"),
                        "agreement_ratio": outcome.get("agreement_ratio"),
                        "critique": outcome.get("critique"),
                        "revised": outcome.get("revised"),
                        "trace": outcome.get("trace", []),
                    }
            except Exception as e:
                logger.info(f"[reasoning_engine] deliberative reasoning failed, falling back: {e}")

        if complexity == "complex" and self._multi is not None:
            try:
                outcome = self._multi.run(goal)
                if "error" not in outcome:
                    return DEPTH_MULTI, {
                        "depth": DEPTH_MULTI,
                        "goal": goal,
                        "conclusion": outcome.get("final_answer", ""),
                        "trace": outcome.get("trace", []),
                    }
            except Exception as e:
                logger.info(f"[reasoning_engine] multi-pass reasoning failed, falling back: {e}")

        if self._single is not None:
            try:
                outcome = self._single.reason(goal)
                if "error" not in outcome:
                    return DEPTH_SINGLE, {
                        "depth": DEPTH_SINGLE,
                        "goal": goal,
                        "conclusion": outcome.get("conclusion") or outcome.get("reasoning", ""),
                        "trace": [outcome.get("reasoning", "")],
                    }
            except Exception as e:
                logger.info(f"[reasoning_engine] single-pass reasoning failed: {e}")

        # Nothing available/working - degrade to pass-through rather than raise.
        return DEPTH_NONE, {
            "depth": DEPTH_NONE,
            "goal": goal,
            "conclusion": goal,
            "trace": ["reasoning backends unavailable - passed goal straight through"],
        }

    def _log_trace(self, goal: str, depth: str, result: Dict) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO reasoning_traces (goal, depth, conclusion, trace_json, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (goal, depth, result.get("conclusion", ""), json.dumps(result.get("trace", []), default=str), now),
            )
            self._conn.commit()

    def get_trace(self, goal: str, limit: int = 1) -> list:
        """Most recent reasoning trace(s) logged for a given goal string
        (exact match) - useful for self_critique.py/verification_engine.py
        to look back at *why* a conclusion was reached."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT depth, conclusion, trace_json, timestamp FROM reasoning_traces
                   WHERE goal = ? ORDER BY id DESC LIMIT ?""",
                (goal, limit),
            ).fetchall()
        out = []
        for depth, conclusion, trace_json, ts in rows:
            try:
                trace = json.loads(trace_json)
            except Exception:
                trace = []
            out.append({"depth": depth, "conclusion": conclusion, "trace": trace, "timestamp": ts})
        return out


def get_reasoning_engine() -> CognitiveReasoningEngine:
    """Process-wide CognitiveReasoningEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CognitiveReasoningEngine()
    return _instance
