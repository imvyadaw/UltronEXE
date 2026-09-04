"""
Goal Planner (Phase 23.3 - Cognitive Reasoning Layer)
=========================================================
Third stage of the Phase 23 cognitive loop (see intent_analyzer.py's
header for the full pipeline diagram). Turns a goal string - typically
intent_analyzer.py's primary_intent plus reasoning_engine.py's
conclusion - into an ordered plan of concrete steps, each with a
rough risk label, then (optionally) registers the goal and its steps
into intelligence.goal_manager so the rest of that package's machinery
(progress_tracker.py, pause_resume.py, recovery_manager.py) can track
it through to completion.

Two planning strategies, LLM first with a deterministic fallback:
    1. LLM-authored plan - richer, can reason about ordering/risk for
       goals that don't fit any hardcoded shape.
    2. intelligence.goal_manager.goal_decomposer's rule-based templates
       - zero-cost, always available, used when the LLM path is
       unavailable or returns something unusable.

Distinct from ai/planning.py: that module plans a sequence of *tool
calls* against ai/tools_schema.py for core/executor.py to run
immediately. This module plans a sequence of *goal steps* - higher
level, meant to be tracked/paused/resumed over time via goal_manager,
not executed in one shot. decision_engine.py downstream is what turns
an individual step into an actual go/no-go call.

Storage: database/goal_planner.db, table plans - this module's own
record of the plan it produced, separate from goal_manager's own
goals.db (which only exists if a plan is actually registered there).
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

    logger = get_logger("ultron.goal_planner")
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("ultron.goal_planner")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from ai.ai_router import get_router
except Exception as exc:  # pragma: no cover
    get_router = None
    logger.warning(f"[goal_planner] ai.ai_router unavailable, LLM planning disabled: {exc}")

try:
    from intelligence.goal_manager.goal_decomposer import get_goal_decomposer
    from intelligence.goal_manager.goal_store import get_goal_store
except Exception as exc:  # pragma: no cover
    get_goal_decomposer = None
    get_goal_store = None
    logger.warning(f"[goal_planner] intelligence.goal_manager unavailable, registration disabled: {exc}")

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "goal_planner.db"

_instance: Optional["GoalPlanner"] = None
_instance_lock = threading.Lock()

PLAN_PROMPT = """Break the goal below into 2-6 ordered, concrete steps needed to
accomplish it. Respond with ONLY a JSON array, nothing else - no prose, no
markdown code fences:
[{{"step": "short description", "risk": "low|medium|high"}}, ...]

Goal: {goal}"""


class GoalPlanner:
    """plan(goal) -> ordered steps; register(plan) -> hooks it into goal_manager."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT,
                strategy TEXT,
                steps_json TEXT,
                registered_goal_id TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._decomposer = get_goal_decomposer() if get_goal_decomposer else None
        self._store = get_goal_store() if get_goal_store else None

    def plan(self, goal: str, description: str = "", register: bool = False) -> Dict:
        """Produce an ordered plan for `goal`. If `register` is True and
        intelligence.goal_manager is available, also creates the goal
        and writes its steps there, returning the goal_id."""
        goal = (goal or "").strip()
        if not goal:
            return {"error": "empty goal"}

        steps, strategy = self._plan_with_llm(goal), "llm"
        if not steps:
            steps, strategy = self._plan_with_decomposer(goal, description), "rule_based"
        if not steps:
            steps, strategy = [{"step": goal, "risk": "medium"}], "single_step_fallback"

        registered_goal_id = None
        if register and self._store is not None:
            registered_goal_id = self._register(goal, description, steps)

        result = {
            "goal": goal,
            "strategy": strategy,
            "steps": steps,
            "step_count": len(steps),
            "registered_goal_id": registered_goal_id,
        }
        self._log_plan(result)
        return result

    def _plan_with_llm(self, goal: str) -> Optional[List[Dict]]:
        if get_router is None:
            return None
        try:
            raw = get_router().complete(PLAN_PROMPT.format(goal=goal), temperature=0.3, max_tokens=500)
            text = raw.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                text = match.group(0)
            parsed = json.loads(text)
            if not isinstance(parsed, list) or not parsed:
                return None
            steps = []
            for item in parsed:
                if isinstance(item, dict) and item.get("step"):
                    risk = item.get("risk") if item.get("risk") in ("low", "medium", "high") else "medium"
                    steps.append({"step": str(item["step"]), "risk": risk})
            return steps or None
        except Exception as e:
            logger.info(f"[goal_planner] LLM planning failed, falling back: {e}")
            return None

    def _plan_with_decomposer(self, goal: str, description: str) -> Optional[List[Dict]]:
        if self._decomposer is None:
            return None
        try:
            raw_steps = self._decomposer.decompose(goal, description)
            return [{"step": s, "risk": "medium"} for s in raw_steps]
        except Exception as e:
            logger.info(f"[goal_planner] rule-based decomposition failed: {e}")
            return None

    def _register(self, goal: str, description: str, steps: List[Dict]) -> Optional[str]:
        try:
            created = self._store.create_goal(title=goal, description=description)
            if created.get("error"):
                return None
            goal_id = created["id"]
            for i, item in enumerate(steps):
                self._store.add_step(goal_id, item["step"], order_index=i)
            return goal_id
        except Exception as e:
            logger.warning(f"[goal_planner] failed to register plan with goal_manager: {e}")
            return None

    def _log_plan(self, result: Dict) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO plans (goal, strategy, steps_json, registered_goal_id, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    result["goal"],
                    result["strategy"],
                    json.dumps(result["steps"], default=str),
                    result.get("registered_goal_id"),
                    now,
                ),
            )
            self._conn.commit()

    def recent_plans(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT goal, strategy, steps_json, registered_goal_id, timestamp
                   FROM plans ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        out = []
        for goal, strategy, steps_json, registered_goal_id, ts in rows:
            try:
                steps = json.loads(steps_json)
            except Exception:
                steps = []
            out.append(
                {
                    "goal": goal,
                    "strategy": strategy,
                    "steps": steps,
                    "registered_goal_id": registered_goal_id,
                    "timestamp": ts,
                }
            )
        return out


def get_goal_planner() -> GoalPlanner:
    """Process-wide GoalPlanner singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GoalPlanner()
    return _instance
