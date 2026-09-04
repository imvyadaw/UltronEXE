"""
ULTRON Advanced Autonomy Fabric
===============================
A composition layer for the existing ULTRON subsystems.

Lifecycle:
    OBSERVE -> MODEL -> MISSION -> RESEARCH -> ACT -> VERIFY -> LEARN

This module intentionally does NOT grant new unrestricted OS/network powers.
Actions continue through ULTRON's existing capability/permission pipeline.
Code evolution remains sandbox-first and never deploys automatically.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.advanced_autonomy")

DB_PATH = Path(__file__).resolve().parents[2] / "database" / "advanced_autonomy.db"

_instance = None
_lock = threading.Lock()


class AdvancedAutonomy:
    """Stateful coordinator that joins already-implemented ULTRON subsystems."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS lifecycle_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS learned_strategies(
                key TEXT PRIMARY KEY,
                strategy TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                uses INTEGER NOT NULL DEFAULT 0,
                successes INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )"""
        )
        self._conn.commit()

    def _event(self, kind: str, payload: Dict[str, Any]) -> None:
        try:
            with self._db_lock:
                self._conn.execute(
                    "INSERT INTO lifecycle_events(kind,payload,created_at) VALUES(?,?,?)",
                    (kind, json.dumps(payload, default=str), time.time()),
                )
                self._conn.commit()
        except Exception:
            logger.exception("advanced lifecycle event persistence failed")

    def observe(self, reason: str = "turn") -> Dict[str, Any]:
        """Capture a fresh world snapshot and return a compact world model."""
        result: Dict[str, Any] = {"reason": reason, "timestamp": time.time()}
        try:
            from intelligence.world_state import get_world_state_manager
            result["world_state"] = get_world_state_manager().capture_full_state()
        except Exception as exc:
            result["world_state_error"] = str(exc)
        self._event("observe", {"reason": reason, "sections": list(result.keys())})
        return result

    def create_mission(self, title: str, description: str = "", context: Optional[Dict] = None) -> Dict:
        from intelligence.mission_engine import get_mission_manager
        mission = get_mission_manager().create_mission(title, description, context or {})
        self._event("mission_created", {"mission_id": mission.get("id"), "title": title})
        return mission

    def checkpoint(self, mission_id: str, note: str, state: Optional[Dict] = None) -> Dict:
        from intelligence.mission_engine import get_mission_manager
        result = get_mission_manager().checkpoint(mission_id, note, state)
        self._event("mission_checkpoint", {"mission_id": mission_id, "note": note})
        return result

    def research(self, query: str, ai_router=None, store_summary: bool = True) -> Dict:
        """Run bounded multi-source research and optionally persist a source-tagged summary."""
        from skills.web.research import WebResearch
        researcher = WebResearch(ai_router=ai_router)
        result = researcher.research(query, num_queries=3, results_per_query=3)
        if result.get("success") and store_summary:
            summary = result.get("summary")
            if summary:
                try:
                    from intelligence.knowledge_os import get_knowledge_os
                    get_knowledge_os().remember_fact(
                        subject=query,
                        predicate="researched_summary",
                        fact_text=summary[:12000],
                        source="web_research",
                        confidence=0.65,
                    )
                    result["stored_in_knowledge_os"] = True
                except Exception as exc:
                    result["knowledge_store_error"] = str(exc)
        self._event(
            "research",
            {
                "query": query,
                "success": bool(result.get("success")),
                "sources_read": result.get("sources_read", 0),
            },
        )
        return result

    def learn_outcome(
        self,
        action_name: str,
        success: bool,
        context: Optional[Dict] = None,
        reward: Optional[float] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an action outcome and update a lightweight strategy score."""
        from learning.experience import get_experience_store

        store = get_experience_store()
        experience_id = store.add_experience(
            action_name,
            success,
            context=context or {},
            reward=reward,
            error=error,
            source="advanced_autonomy",
        )
        key = action_name.strip().lower() or "unknown"
        now = time.time()
        with self._db_lock:
            row = self._conn.execute(
                "SELECT strategy,confidence,uses,successes FROM learned_strategies WHERE key=?",
                (key,),
            ).fetchone()
            if row:
                strategy, confidence, uses, successes = row
                uses += 1
                successes += int(bool(success))
                observed = successes / max(1, uses)
                confidence = round((confidence * 0.7) + (observed * 0.3), 4)
                self._conn.execute(
                    "UPDATE learned_strategies SET confidence=?,uses=?,successes=?,updated_at=? WHERE key=?",
                    (confidence, uses, successes, now, key),
                )
            else:
                self._conn.execute(
                    "INSERT INTO learned_strategies(key,strategy,confidence,uses,successes,updated_at) VALUES(?,?,?,?,?,?)",
                    (key, "reuse previously successful execution pattern", 1.0 if success else 0.0, 1, int(bool(success)), now),
                )
            self._conn.commit()
        self._event("learn", {"action": action_name, "success": success, "experience_id": experience_id})
        return self.strategy(action_name)

    def strategy(self, action_name: str) -> Dict[str, Any]:
        key = action_name.strip().lower() or "unknown"
        with self._db_lock:
            row = self._conn.execute(
                "SELECT strategy,confidence,uses,successes,updated_at FROM learned_strategies WHERE key=?",
                (key,),
            ).fetchone()
        if not row:
            return {"action": action_name, "known": False, "confidence": 0.0}
        return {
            "action": action_name,
            "known": True,
            "strategy": row[0],
            "confidence": row[1],
            "uses": row[2],
            "successes": row[3],
            "updated_at": row[4],
        }

    def safe_evaluate_evolution(self, project_root: str) -> Dict[str, Any]:
        """Evaluate a possible code evolution; never deploys the result."""
        from self_evolution.evolution_manager import EvolutionManager
        result = EvolutionManager().evaluate(project_root)
        self._event(
            "evolution_evaluated",
            {
                "project_root": project_root,
                "accepted": bool(result.get("accepted")),
                "deployed": False,
            },
        )
        result["deployment"] = {
            "performed": False,
            "reason": "Advanced Autonomy is sandbox-first; production deployment requires explicit human approval.",
        }
        return result

    def status(self) -> Dict[str, Any]:
        with self._db_lock:
            events = self._conn.execute("SELECT COUNT(*) FROM lifecycle_events").fetchone()[0]
            strategies = self._conn.execute("SELECT COUNT(*) FROM learned_strategies").fetchone()[0]
        return {
            "engine": "ULTRON Advanced Autonomy Fabric",
            "lifecycle": ["observe", "model", "mission", "research", "act", "verify", "learn"],
            "events": events,
            "learned_strategies": strategies,
            "safety": {
                "existing_permission_pipeline_preserved": True,
                "sandbox_first_evolution": True,
                "automatic_production_deploy": False,
            },
        }


def get_advanced_autonomy() -> AdvancedAutonomy:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = AdvancedAutonomy()
    return _instance
