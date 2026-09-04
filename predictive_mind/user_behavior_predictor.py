"""
User behavior predictor
=========================
Reads proactive/predictor.py's own SQLite store (database/
proactive_predictor.db, proactive.predictor.DB_PATH) READ-ONLY for
aggregate stats, and calls its public predict_next()/predict_routine()
for the actual predictions - this module never writes to that
database (observe() stays the single write path, owned by
predictor.py) and never touches ActionPredictor's private connection.

get_behavior_profile() is the "how do I usually use you" answer:
busiest hour-of-day buckets, most-used actions/categories, and the
current routine prediction (if any), all in one call - the analysis
proactive/predictor.py itself doesn't build.
"""

import sqlite3
import time
from typing import Dict, List, Optional

from core.logger import get_logger

logger = get_logger("user_behavior_predictor")


def _read_only_connection() -> Optional[sqlite3.Connection]:
    from proactive.predictor import DB_PATH

    if not DB_PATH.exists():
        return None
    try:
        # uri=True + mode=ro: never contend with ActionPredictor's own
        # write connection, and never accidentally create/alter the file.
        return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    except Exception as e:
        logger.info("Could not open predictor DB read-only: %s", e)
        return None


def predict_next_action(top_k: int = 3) -> List[Dict]:
    """Thin passthrough to proactive.predictor.get_action_predictor()
    .predict_next() - kept here so callers only need one import for
    both the raw prediction and the richer profile below."""
    from proactive.predictor import get_action_predictor

    return get_action_predictor().predict_next(top_k=top_k)


def get_behavior_profile(top_n: int = 5) -> Dict:
    """Returns:
        {
          "success": bool,
          "total_observations": int,
          "top_actions": [{"action_name": str, "count": int}, ...],
          "top_categories": [{"category": str, "count": int}, ...],
          "busiest_hours": [{"hour": int, "count": int}, ...],
          "predicted_routine": {...} | None,
          "next_action_predictions": [...],
        }
    Returns success=False with empty stats (not an error) if no
    observations have been recorded yet - a brand-new install with an
    empty predictor DB is an expected, not exceptional, state."""
    conn = _read_only_connection()
    if conn is None:
        return {
            "success": False,
            "total_observations": 0,
            "top_actions": [],
            "top_categories": [],
            "busiest_hours": [],
            "predicted_routine": None,
            "next_action_predictions": [],
            "reason": "no observation history yet",
        }

    try:
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        if not total:
            return {
                "success": False,
                "total_observations": 0,
                "top_actions": [],
                "top_categories": [],
                "busiest_hours": [],
                "predicted_routine": None,
                "next_action_predictions": [],
                "reason": "no observation history yet",
            }

        top_actions = [
            {"action_name": row[0], "count": row[1]}
            for row in conn.execute(
                "SELECT action_name, COUNT(*) c FROM observations " "GROUP BY action_name ORDER BY c DESC LIMIT ?",
                (top_n,),
            ).fetchall()
        ]
        top_categories = [
            {"category": row[0], "count": row[1]}
            for row in conn.execute(
                "SELECT category, COUNT(*) c FROM observations " "GROUP BY category ORDER BY c DESC LIMIT ?", (top_n,)
            ).fetchall()
        ]
        # time_bucket is (hour*60+minute)//30 -> hour = bucket // 2
        busiest_hours = [
            {"hour": row[0], "count": row[1]}
            for row in conn.execute(
                "SELECT (time_bucket / 2) AS hour, COUNT(*) c FROM observations "
                "GROUP BY hour ORDER BY c DESC LIMIT ?",
                (top_n,),
            ).fetchall()
        ]
    finally:
        conn.close()

    try:
        from proactive.predictor import get_action_predictor

        predictor = get_action_predictor()
        routine = predictor.predict_routine(now=time.time())
        next_actions = predictor.predict_next(top_k=3)
    except Exception as e:
        logger.info("Could not fetch live predictions for behavior profile: %s", e)
        routine, next_actions = None, []

    return {
        "success": True,
        "total_observations": total,
        "top_actions": top_actions,
        "top_categories": top_categories,
        "busiest_hours": busiest_hours,
        "predicted_routine": routine,
        "next_action_predictions": next_actions,
    }
