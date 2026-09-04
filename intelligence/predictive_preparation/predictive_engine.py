"""
Predictive Engine (Phase 20.2 - Predictive Preparation)
==================================================
Single entry point for the predictive_preparation/ package - mirrors
proactive_engine.py's role in Phase 20.1 (a thin orchestrator over
otherwise-independent sub-modules that still work fine called
directly). Two calls are all a caller needs:

    record_task()        - tell this module a task just started/ran,
                            so next_task_predictor.py can learn from
                            it. Optionally also triggers a fresh
                            prediction+prepare pass right away.
    predict_and_prepare() - ask what's likely next and, for whatever
                            clears the confidence threshold, dispatch
                            preloading to app_preloader.py/
                            model_preloader.py/context_preloader.py
                            (each of which independently checks
                            resource_optimizer.py before doing
                            anything).

Pipeline per prediction that clears MIN_CONFIDENCE_TO_PREPARE:

    next_task_predictor.py  -> predicted task_type + confidence
    app_preloader.py        -> preload any mapped app, if resources allow
    model_preloader.py      -> warm any mapped model, if resources allow
    context_preloader.py    -> prefetch any mapped context, if resources allow

Only the top MAX_PREDICTIONS_TO_ACT_ON predictions are acted on even
if more clear the confidence bar - acting on every plausible guess
defeats the resource discipline resource_optimizer.py is there to
enforce.

Storage: database/predictive_preparation.db, table
predictive_preparation_events (this module's own table, logging the
full pipeline outcome per prediction pass; next_task_predictor.py/
app_preloader.py/model_preloader.py/context_preloader.py each keep
their own tables in the same database file).

Purely additive - nothing in Phase 1-20 imports from here, and this
module does not import from proactive_intelligence/ (Phase 20.1)
either. The two packages solve different problems (what to say vs.
what to have ready) and can be wired together by a caller that wants
both, but neither depends on the other.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.predictive_preparation.next_task_predictor import get_next_task_predictor
from intelligence.predictive_preparation.resource_optimizer import get_resource_optimizer
from intelligence.predictive_preparation.app_preloader import get_app_preloader
from intelligence.predictive_preparation.model_preloader import get_model_preloader
from intelligence.predictive_preparation.context_preloader import get_context_preloader

logger = get_logger("ultron.predictive_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "predictive_preparation.db"

_instance: Optional["PredictiveEngine"] = None
_instance_lock = threading.Lock()

# a prediction below this confidence isn't acted on - it's returned to
# the caller for visibility, but nothing gets preloaded on its behalf
MIN_CONFIDENCE_TO_PREPARE = 0.35

# even with more predictions clearing the bar above, only the
# top-scoring few are actually dispatched to the preloaders - keeps
# a single task completion from fanning out into a burst of
# speculative work
MAX_PREDICTIONS_TO_ACT_ON = 2


class PredictiveEngine:
    """Orchestrates next_task_predictor / resource_optimizer /
    app_preloader / model_preloader / context_preloader into the two
    calls a caller needs: record_task() and predict_and_prepare()."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS predictive_preparation_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                current_task TEXT,
                predicted_task TEXT,
                confidence REAL,
                acted_on INTEGER,
                results_json TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._predictor = get_next_task_predictor()
        self._resource = get_resource_optimizer()
        self._apps = get_app_preloader()
        self._models = get_model_preloader()
        self._contexts = get_context_preloader()

    def record_task(
        self,
        task_type: str,
        category: Optional[str] = None,
        context: Optional[Dict] = None,
        session_id: Optional[str] = None,
        auto_prepare: bool = True,
    ) -> Dict:
        """Learn from a task that just started/ran. If auto_prepare,
        immediately runs a predict_and_prepare() pass using this task
        as current_task, so preparation for whatever's likely next
        starts right away rather than waiting on a separate call."""
        recorded = self._predictor.record_task(task_type, category=category, context=context)
        result = {"recorded": recorded, "prepared": None}
        if auto_prepare:
            result["prepared"] = self.predict_and_prepare(
                current_task=task_type,
                context=context,
                session_id=session_id,
            )
        return result

    def predict_and_prepare(
        self, current_task: Optional[str] = None, context: Optional[Dict] = None, session_id: Optional[str] = None
    ) -> Dict:
        """The one call a caller needs to both ask what's likely next
        and have this module act on it where confidence and resources
        allow. Always returns the full prediction list, even for
        predictions that weren't acted on."""
        prediction = self._predictor.predict_next(
            current_task=current_task,
            context=context,
            top_n=MAX_PREDICTIONS_TO_ACT_ON + 1,
        )
        predictions = prediction["predictions"]

        acted = []
        for pred in predictions:
            if len(acted) >= MAX_PREDICTIONS_TO_ACT_ON:
                break
            if pred["confidence"] < MIN_CONFIDENCE_TO_PREPARE:
                self._log_event(session_id, current_task, pred, acted_on=False, results=None)
                continue

            task_type = pred["task_type"]
            confidence = pred["confidence"]
            results = {
                "app": self._apps.preload_for_task(task_type, confidence, context),
                "model": self._models.preload_for_task(task_type, confidence, context),
                "context": self._contexts.preload_for_task(task_type, confidence, context),
            }
            acted.append({"task_type": task_type, "confidence": confidence, "results": results})
            self._log_event(session_id, current_task, pred, acted_on=True, results=results)

        if acted:
            logger.info(
                f"predictive_engine: prepared for {len(acted)} predicted task(s) " f"following '{current_task}'"
            )

        return {"predictions": predictions, "acted": acted, "reasons": prediction.get("reasons", [])}

    def get_resource_snapshot(self) -> Dict:
        return self._resource.get_current_load()

    def get_recent_events(self, session_id: Optional[str] = None, limit: int = 20) -> List[Dict]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    """SELECT id, session_id, current_task, predicted_task, confidence,
                              acted_on, results_json, timestamp
                       FROM predictive_preparation_events WHERE session_id = ? ORDER BY id DESC LIMIT ?""",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT id, session_id, current_task, predicted_task, confidence,
                              acted_on, results_json, timestamp
                       FROM predictive_preparation_events ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        events = []
        for id_, sid, current_task, predicted_task, confidence, acted_on, results_json, timestamp in rows:
            try:
                results = json.loads(results_json) if results_json else None
            except Exception:
                results = None
            events.append(
                {
                    "id": id_,
                    "session_id": sid,
                    "current_task": current_task,
                    "predicted_task": predicted_task,
                    "confidence": confidence,
                    "acted_on": bool(acted_on),
                    "results": results,
                    "timestamp": timestamp,
                }
            )
        return events

    def _log_event(
        self,
        session_id: Optional[str],
        current_task: Optional[str],
        pred: Dict,
        acted_on: bool,
        results: Optional[Dict],
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO predictive_preparation_events
                   (session_id, current_task, predicted_task, confidence, acted_on, results_json, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    current_task,
                    pred["task_type"],
                    pred["confidence"],
                    1 if acted_on else 0,
                    json.dumps(results) if results else None,
                    now,
                ),
            )
            self._conn.commit()


def get_predictive_engine() -> PredictiveEngine:
    """Process-wide PredictiveEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PredictiveEngine()
    return _instance
