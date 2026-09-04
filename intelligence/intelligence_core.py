"""
Intelligence Core (Phase 20.5)
=============================
Single top-level entry point for ULTRON's whole intelligence layer -
the same "orchestrator ties otherwise-independent sub-modules
together, they still work fine called directly" role
performance_engine.py plays for adaptive_performance/ (Phase 20.3) and
predictive_engine.py plays for predictive_preparation/ (Phase 20.2),
just one level up: this ties together all 13 bridges intelligence_bridge/
(Phase 20.4) exposes, rather than one package's own sub-modules.

Two ways to use it:

    1. process_turn() - one call per user turn that runs the full
       pipeline below and returns a single consolidated result. Good
       for a caller that just wants "the intelligence layer's take on
       this turn" without wiring 13 bridges together itself.
    2. The individual bridges via self.bridge.<name> (an
       intelligence_bridge.IntelligenceBridge) - for a caller that
       wants one piece (e.g. just confidence scoring) without paying
       for the rest of the pipeline.

process_turn() pipeline (each step best-effort via intelligence_bridge/,
which already degrades any missing subsystem to a harmless no-op - see
intelligence_bridge/_bridge_utils.py):

    conversation.add_turn()   -> log the incoming turn
    world_state.get_state()   -> what's true right now
    intent.classify()         -> what the user wants
    confidence.should_clarify() -> if too unsure, short-circuit here
                                    and return a clarify-first result
                                    without running the rest
    knowledge.query()         -> anything already known that's relevant
    goal.plan()                -> only if intent looks goal-shaped
    proactive.should_speak()  -> whether ULTRON should also say
                                    something unprompted this turn
    predictive.predict_next() -> best-effort guess at what's next,
                                    for a caller that wants to warm
                                    something up

Any actual provider/tool call the caller makes as a result of this
pipeline is its own concern - record_provider_call()/handle_error()/
remember() below are separate best-effort hooks back into
performance_bridge/healing_bridge/knowledge_bridge for a caller that
wants to report the outcome, not something process_turn() does itself
(mirrors performance_engine.py's plan_call()/record_call() staying two
separate calls around the real work rather than one that does the
work itself).

Storage: database/intelligence_core.db, table intelligence_events -
one row per process_turn() call, logging what each step returned (or
skipped) for later inspection. Owns only this table; every bridge's
own subsystem keeps its own tables, same sharing pattern as
performance_metrics.db.

Phase 28: get_user_profile()/update_user_profile() and
record_emotion()/get_emotional_history()/get_latest_emotion() below
read/write database/intelligence/user_profiles.db and
emotional_history.db directly via self.db (database_manager.py) -
see database_manager.py's own Phase 28 note for why these two skip
the bridge layer that goals/skills/knowledge/world_state go through.

Purely additive - nothing in Phase 1-20 imports from here. Does not
modify intelligence_bridge/ or anything it bridges to; if
intelligence_bridge/ itself isn't importable (e.g. this file used
outside the full ULTRON repo), IntelligenceCore degrades to reporting
itself unavailable rather than raising, same posture every bridge it
wraps already has.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from core.logger import get_logger

    logger = get_logger("ultron.intelligence_core")
except Exception:
    import logging

    logger = logging.getLogger("ultron.intelligence_core")
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO)

try:
    from intelligence_bridge import get_intelligence_bridge

    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - only hit if 20.4 isn't present
    get_intelligence_bridge = None
    _IMPORT_ERROR = exc

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "intelligence_core.db"

try:
    from database import get_database_manager

    _DB_IMPORT_ERROR = None
except Exception as exc:
    get_database_manager = None
    _DB_IMPORT_ERROR = exc

_instance: Optional["IntelligenceCore"] = None
_instance_lock = threading.Lock()

_MISSING = object()


class IntelligenceCore:
    """Orchestrates all 13 intelligence_bridge/ bridges into one
    process_turn() entry point, while leaving each bridge fully usable
    on its own via self.bridge.<name>."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db = None
        if get_database_manager is not None:
            try:
                self.db = get_database_manager()
                logger.info("[intelligence_core] Phase 20.6 databases connected")
            except Exception:
                logger.exception("[intelligence_core] Phase 20.6 database layer unavailable")

        self.bridge = None
        if get_intelligence_bridge is not None:
            try:
                self.bridge = get_intelligence_bridge()
                logger.info("[intelligence_core] connected to intelligence_bridge")
            except Exception:
                logger.exception("[intelligence_core] intelligence_bridge imported but failed to initialize")
        else:
            logger.info(
                "[intelligence_core] intelligence_bridge not found (%s) - " "running in degraded/no-op mode",
                _IMPORT_ERROR,
            )

        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = None
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS intelligence_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT,
                    user_input TEXT,
                    intent TEXT,
                    confidence TEXT,
                    should_clarify INTEGER,
                    result_json TEXT,
                    timestamp REAL
                )""")
            self._conn.commit()
        except Exception:
            logger.exception("[intelligence_core] could not open %s - event logging disabled", self._db_path)
            self._conn = None

    def is_available(self) -> bool:
        return self.bridge is not None

    def status(self) -> Dict[str, Any]:
        """Availability of intelligence_core itself plus all 13
        bridges it orchestrates, in one call."""
        return {
            "intelligence_core_available": self.is_available(),
            "event_logging_available": self._conn is not None,
            "phase_20_6_database_available": self.db is not None,
            "databases": self.db.status() if self.db is not None else {},
            "bridges": self.bridge.status() if self.is_available() else {},
        }

    # ------------------------------------------------------------------
    # main pipeline
    # ------------------------------------------------------------------

    def process_turn(self, user_input: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Run the full best-effort intelligence pipeline for one user
        turn and return a consolidated result. Every step is optional -
        a missing/unavailable subsystem just leaves that key None in
        the result instead of failing the whole call. Never raises."""
        turn_id = str(uuid.uuid4())
        context = context or {}
        result: Dict[str, Any] = {
            "turn_id": turn_id,
            "conversation_logged": False,
            "world_state": None,
            "intent": None,
            "confidence": None,
            "should_clarify": None,
            "knowledge": None,
            "goal_plan": None,
            "proactive": None,
            "predicted_next": None,
            "stopped_early": False,
        }

        # Phase 20.6 persistence starts even when the optional bridge layer is
        # unavailable, so a degraded IntelligenceCore still keeps conversation
        # history instead of silently losing the turn.
        if self.db is not None:
            try:
                self.db.record_conversation("user", user_input, context=context, turn_id=turn_id)
                result["conversation_logged"] = True
            except Exception:
                logger.exception("[intelligence_core] conversation history persistence failed")

        if not self.is_available():
            logger.info("[intelligence_core] process_turn() called with no intelligence_bridge available")
            self._log_event(turn_id, user_input, result)
            return result

        b = self.bridge

        bridge_logged = b.conversation.add_turn("user", user_input, context=context)
        result["conversation_logged"] = bool(bridge_logged) or result["conversation_logged"]

        result["world_state"] = b.world_state.get_state()

        result["intent"] = b.intent.classify(user_input, context={**context, "world_state": result["world_state"]})

        result["confidence"] = b.confidence.score(result["intent"], context=context)
        if self.db is not None and isinstance(result["confidence"], (int, float)):
            try:
                self.db.record_confidence(
                    float(result["confidence"]),
                    "scored",
                    turn_id=turn_id,
                    intent=str(result["intent"]),
                    context=context,
                )
            except Exception:
                logger.exception("[intelligence_core] confidence persistence failed")
        should_clarify = b.confidence.should_clarify(
            context={**context, "intent": result["intent"], "confidence": result["confidence"]}
        )
        result["should_clarify"] = bool(should_clarify) if should_clarify is not None else None

        if result["should_clarify"]:
            # Low enough confidence that the rest of the pipeline (goal
            # planning especially) isn't worth running yet - a caller
            # should ask a clarifying question instead of acting.
            result["stopped_early"] = True
            self._log_event(turn_id, user_input, result)
            return result

        result["knowledge"] = b.knowledge.query(user_input, context=context)

        result["goal_plan"] = b.goal.plan(user_input, context={**context, "intent": result["intent"]})

        result["proactive"] = b.proactive.should_speak(context={**context, "world_state": result["world_state"]})

        result["predicted_next"] = b.predictive.predict_next(context={**context, "intent": result["intent"]})

        self._log_event(turn_id, user_input, result)
        return result

    # ------------------------------------------------------------------
    # separate best-effort hooks a caller reports outcomes back through
    # ------------------------------------------------------------------

    def record_provider_call(
        self,
        operation: str,
        provider: str,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        call_id: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Report the outcome of a real provider/tool call made as a
        result of a turn - feeds performance_bridge (routing/caching),
        skill_learning_bridge (if `skill` given), and healing_bridge
        (only on failure)."""
        outcome: Dict[str, Any] = {"recorded": False, "diagnosis": None, "repair": None}
        if not self.is_available():
            return outcome

        call_id = call_id or str(uuid.uuid4())
        record = self.bridge.performance.record_call(
            call_id,
            operation,
            provider,
            latency_ms,
            success=success,
            error=error,
        )
        if self.db is not None:
            try:
                self.db.record_provider_call(
                    call_id,
                    operation,
                    provider,
                    latency_ms,
                    success=success,
                    error=error,
                    skill=skill,
                )
            except Exception:
                logger.exception("[intelligence_core] performance persistence failed")
        outcome["recorded"] = record is not None

        if skill is not None:
            self.bridge.skill_learning.record_outcome(
                skill, success, context={"operation": operation, "provider": provider}
            )

        if not success:
            outcome["diagnosis"] = self.bridge.healing.diagnose(
                error, context={"operation": operation, "provider": provider}
            )
            outcome["repair"] = self.bridge.healing.attempt_repair(
                error, context={"operation": operation, "provider": provider}
            )

        return outcome

    def handle_error(self, error: Any, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Standalone diagnose+repair hook for an error not tied to a
        provider call (e.g. a tool execution failure)."""
        if not self.is_available():
            return {"diagnosis": None, "repair": None}
        return {
            "diagnosis": self.bridge.healing.diagnose(error, context=context),
            "repair": self.bridge.healing.attempt_repair(error, context=context),
        }

    def remember(self, fact: str) -> bool:
        """Store `fact` via knowledge_bridge for later recall."""
        if not self.is_available():
            return False
        return self.bridge.knowledge.remember(fact)

    def recall(self, question: str) -> Optional[Any]:
        """Query knowledge_bridge for `question`."""
        if not self.is_available():
            return None
        return self.bridge.knowledge.query(question)

    # ------------------------------------------------------------------
    # Phase 28: user profiles / emotional history
    # ------------------------------------------------------------------
    # Both go straight through self.db (database_manager.py) rather than
    # a bridge - unlike goals/skills/knowledge/world_state, neither
    # user_profiles.db nor emotional_history.db maps to an existing
    # intelligence/ subsystem for intelligence_bridge/ to bridge onto,
    # so this is the same direct-self.db pattern process_turn() already
    # uses for conversation_history.db and confidence_history.db above.

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return self.db.get_user_profile(user_id)
        except Exception:
            logger.exception("[intelligence_core] get_user_profile failed")
            return None

    def update_user_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None,
        traits: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if self.db is None:
            return False
        try:
            self.db.upsert_user_profile(
                user_id, display_name=display_name, preferences=preferences, traits=traits, metadata=metadata
            )
            return True
        except Exception:
            logger.exception("[intelligence_core] update_user_profile failed")
            return False

    def record_emotion(
        self,
        emotion: str,
        intensity: Optional[float] = None,
        user_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source: str = "analysis",
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if self.db is None:
            return None
        try:
            return self.db.record_emotion(
                emotion, intensity=intensity, user_id=user_id, turn_id=turn_id, source=source, context=context
            )
        except Exception:
            logger.exception("[intelligence_core] record_emotion failed")
            return None

    def get_emotional_history(self, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        if self.db is None:
            return []
        try:
            return self.db.get_emotional_history(user_id=user_id, limit=limit)
        except Exception:
            logger.exception("[intelligence_core] get_emotional_history failed")
            return []

    def get_latest_emotion(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return self.db.get_latest_emotion(user_id=user_id)
        except Exception:
            logger.exception("[intelligence_core] get_latest_emotion failed")
            return None

    # ------------------------------------------------------------------
    # event log
    # ------------------------------------------------------------------

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self._conn is None:
            return []
        with self._lock:
            rows = self._conn.execute(
                """SELECT turn_id, user_input, intent, confidence, should_clarify, result_json, timestamp
                   FROM intelligence_events ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        events = []
        for turn_id, user_input, intent, confidence, should_clarify, result_json, ts in rows:
            try:
                result = json.loads(result_json) if result_json else None
            except Exception:
                result = None
            events.append(
                {
                    "turn_id": turn_id,
                    "user_input": user_input,
                    "intent": intent,
                    "confidence": confidence,
                    "should_clarify": bool(should_clarify) if should_clarify is not None else None,
                    "result": result,
                    "timestamp": ts,
                }
            )
        return events

    def _log_event(self, turn_id: str, user_input: str, result: Dict[str, Any]) -> None:
        if self._conn is None:
            return
        try:
            result_json = json.dumps(result, default=str)
        except Exception:
            result_json = None
        try:
            with self._lock:
                self._conn.execute(
                    """INSERT INTO intelligence_events
                       (turn_id, user_input, intent, confidence, should_clarify, result_json, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        turn_id,
                        user_input,
                        str(result.get("intent")),
                        str(result.get("confidence")),
                        None if result.get("should_clarify") is None else (1 if result.get("should_clarify") else 0),
                        result_json,
                        time.time(),
                    ),
                )
                self._conn.commit()
        except Exception:
            logger.exception("[intelligence_core] failed to log event for turn %s", turn_id)


def get_intelligence_core() -> IntelligenceCore:
    """Process-wide IntelligenceCore singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = IntelligenceCore()
    return _instance
