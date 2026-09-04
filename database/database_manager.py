"""
ULTRON Database Manager (Phase 20.6, extended Phase 28)
-------------------------------------
Owns the nine persistent intelligence SQLite databases, kept in their
own database/intelligence/ subfolder specifically so they never
collide with the per-module DB files several Phase 19.x subsystems
already write directly under database/ (e.g. goal_store.py's own
database/goals.db) - same base filenames, different schemas, so
sharing a path would corrupt one or the other's queries. This layer
is additive: existing subsystem stores remain free to use their own
DB connections under database/, while new callers can use one
consistent, thread-safe API for this separate copy.

Databases (under database/intelligence/):
    world_state.db
    goals.db
    learned_skills.db
    knowledge_graph.db
    confidence_history.db
    performance_metrics.db
    conversation_history.db
    user_profiles.db          (Phase 28)
    emotional_history.db      (Phase 28)

Phase 28 note: unlike the first seven, user_profiles.db and
emotional_history.db have no earlier Phase 19.x subsystem already
writing a same-named file elsewhere - there's no separate
"user_profile_manager" or "emotion_tracker" from an earlier phase to
collide with, so these two are simply new stores rather than a
Phase-20.6-style consolidated copy of something older. They're
accessed the same way as the other seven (via this manager's
connection()/execute()/fetchone()/fetchall() plus the dedicated
convenience methods below) and exposed to callers as plain methods on
intelligence.intelligence_core.IntelligenceCore (get_user_profile()/
update_user_profile()/record_emotion()/get_emotional_history()/
get_latest_emotion()) - the same direct-self.db pattern
intelligence_core.py already uses for conversation_history.db and
confidence_history.db, since neither new store maps to one of
intelligence_bridge/'s 13 subsystem bridges.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

DB_DIR = Path(__file__).resolve().parent / "intelligence"
DB_FILES = (
    "world_state.db",
    "goals.db",
    "learned_skills.db",
    "knowledge_graph.db",
    "confidence_history.db",
    "performance_metrics.db",
    "conversation_history.db",
    "user_profiles.db",
    "emotional_history.db",
)


class DatabaseManager:
    def __init__(self, db_dir: Path = DB_DIR):
        self.db_dir = Path(db_dir)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._locks = {name: threading.RLock() for name in DB_FILES}
        self._initialize_all()

    def path(self, name: str) -> Path:
        if name not in DB_FILES:
            raise ValueError(f"Unknown intelligence database: {name}")
        return self.db_dir / name

    def connection(self, name: str) -> sqlite3.Connection:
        if name not in DB_FILES:
            raise ValueError(f"Unknown intelligence database: {name}")
        conns = getattr(self._local, "connections", None)
        if conns is None:
            conns = {}
            self._local.connections = conns
        if name not in conns:
            conn = sqlite3.connect(
                str(self.path(name)),
                timeout=10,
                check_same_thread=True,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conns[name] = conn
        return conns[name]

    def execute(self, name: str, sql: str, params: Sequence[Any] = ()) -> int:
        with self._locks[name]:
            conn = self.connection(name)
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            return cur.rowcount

    def executemany(self, name: str, sql: str, rows: Iterable[Sequence[Any]]) -> int:
        with self._locks[name]:
            conn = self.connection(name)
            cur = conn.executemany(sql, rows)
            conn.commit()
            return cur.rowcount

    def fetchone(self, name: str, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        with self._locks[name]:
            row = self.connection(name).execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def fetchall(self, name: str, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self._locks[name]:
            rows = self.connection(name).execute(sql, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    def record_conversation(
        self, role: str, content: str, context: Optional[Dict[str, Any]] = None, turn_id: Optional[str] = None
    ) -> str:
        turn_id = turn_id or str(uuid.uuid4())
        now = time.time()
        self.execute(
            "conversation_history.db",
            """INSERT OR REPLACE INTO conversation_turns
               (turn_id, role, content, context_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (turn_id, role, content, json.dumps(context or {}, default=str), now),
        )
        return turn_id

    def save_world_state(self, state: Dict[str, Any], source: str = "ultron", snapshot_id: Optional[str] = None) -> str:
        snapshot_id = snapshot_id or str(uuid.uuid4())
        self.execute(
            "world_state.db",
            """INSERT INTO world_state_snapshots
               (snapshot_id, state_json, source, created_at)
               VALUES (?, ?, ?, ?)""",
            (snapshot_id, json.dumps(state, default=str), source, time.time()),
        )
        return snapshot_id

    def upsert_goal(
        self,
        goal_id: str,
        title: str,
        description: str = "",
        status: str = "pending",
        priority: int = 0,
        progress: float = 0.0,
        parent_goal_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = time.time()
        self.execute(
            "goals.db",
            """INSERT INTO goals
               (goal_id,title,description,status,priority,progress,parent_goal_id,metadata_json,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(goal_id) DO UPDATE SET
                 title=excluded.title, description=excluded.description,
                 status=excluded.status, priority=excluded.priority,
                 progress=excluded.progress, parent_goal_id=excluded.parent_goal_id,
                 metadata_json=excluded.metadata_json, updated_at=excluded.updated_at""",
            (
                goal_id,
                title,
                description,
                status,
                int(priority),
                float(progress),
                parent_goal_id,
                json.dumps(metadata or {}, default=str),
                now,
                now,
            ),
        )
        return goal_id

    def upsert_skill(
        self, skill_id: str, name: str, workflow: Dict[str, Any], description: str = "", confidence: float = 0.0
    ) -> str:
        now = time.time()
        self.execute(
            "learned_skills.db",
            """INSERT INTO skills
               (skill_id,name,description,workflow_json,confidence,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(skill_id) DO UPDATE SET
                 name=excluded.name, description=excluded.description,
                 workflow_json=excluded.workflow_json, confidence=excluded.confidence,
                 updated_at=excluded.updated_at""",
            (skill_id, name, description, json.dumps(workflow, default=str), float(confidence), now, now),
        )
        return skill_id

    def upsert_entity(
        self, entity_id: str, entity_type: str, name: str, properties: Optional[Dict[str, Any]] = None
    ) -> str:
        now = time.time()
        self.execute(
            "knowledge_graph.db",
            """INSERT INTO entities(entity_id,entity_type,name,properties_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(entity_id) DO UPDATE SET
                 entity_type=excluded.entity_type, name=excluded.name,
                 properties_json=excluded.properties_json, updated_at=excluded.updated_at""",
            (entity_id, entity_type, name, json.dumps(properties or {}, default=str), now, now),
        )
        return entity_id

    def record_confidence(
        self,
        confidence: float,
        decision: str,
        turn_id: Optional[str] = None,
        intent: Optional[str] = None,
        threshold: Optional[float] = None,
        risk: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        self.execute(
            "confidence_history.db",
            """INSERT INTO confidence_events
               (event_id,turn_id,intent,confidence,threshold,risk,decision,context_json,created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                turn_id,
                intent,
                float(confidence),
                threshold,
                risk,
                decision,
                json.dumps(context or {}, default=str),
                time.time(),
            ),
        )
        return event_id

    def upsert_user_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None,
        traits: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create or update a user's profile. Existing preferences/traits/
        metadata are replaced wholesale by whatever's passed here (not
        merged) - a caller that wants to add one field to an existing
        profile should read it via get_user_profile() first and pass
        the merged dict back. Unset fields (None) are left untouched
        on an existing row rather than wiped, by only including
        columns actually provided in the UPDATE."""
        now = time.time()
        existing = self.get_user_profile(user_id)
        if existing is None:
            self.execute(
                "user_profiles.db",
                """INSERT INTO user_profiles
                   (user_id,display_name,preferences_json,traits_json,metadata_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    user_id,
                    display_name,
                    json.dumps(preferences or {}, default=str),
                    json.dumps(traits or {}, default=str),
                    json.dumps(metadata or {}, default=str),
                    now,
                    now,
                ),
            )
        else:
            self.execute(
                "user_profiles.db",
                """UPDATE user_profiles SET
                     display_name=COALESCE(?, display_name),
                     preferences_json=?, traits_json=?, metadata_json=?, updated_at=?
                   WHERE user_id=?""",
                (
                    display_name,
                    json.dumps(preferences if preferences is not None else existing["preferences"], default=str),
                    json.dumps(traits if traits is not None else existing["traits"], default=str),
                    json.dumps(metadata if metadata is not None else existing["metadata"], default=str),
                    now,
                    user_id,
                ),
            )
        return user_id

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        row = self.fetchone("user_profiles.db", "SELECT * FROM user_profiles WHERE user_id=?", (user_id,))
        if row is None:
            return None
        row["preferences"] = json.loads(row.pop("preferences_json") or "{}")
        row["traits"] = json.loads(row.pop("traits_json") or "{}")
        row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
        return row

    def list_user_profiles(self, limit: int = 100) -> List[Dict[str, Any]]:
        rows = self.fetchall(
            "user_profiles.db",
            "SELECT * FROM user_profiles ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        for row in rows:
            row["preferences"] = json.loads(row.pop("preferences_json") or "{}")
            row["traits"] = json.loads(row.pop("traits_json") or "{}")
            row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
        return rows

    def record_emotion(
        self,
        emotion: str,
        intensity: Optional[float] = None,
        user_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source: str = "analysis",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log one detected/reported emotional data point. `source` is
        a free-text tag for where the reading came from (e.g.
        'mood_analyzer', 'explicit', 'voice_tone') so get_emotional_history()
        callers can tell a keyword-guessed mood apart from one the user
        stated outright."""
        event_id = str(uuid.uuid4())
        self.execute(
            "emotional_history.db",
            """INSERT INTO emotional_events
               (event_id,user_id,turn_id,emotion,intensity,source,context_json,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                event_id,
                user_id,
                turn_id,
                emotion,
                intensity,
                source,
                json.dumps(context or {}, default=str),
                time.time(),
            ),
        )
        return event_id

    def get_emotional_history(self, user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        if user_id:
            rows = self.fetchall(
                "emotional_history.db",
                "SELECT * FROM emotional_events WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            rows = self.fetchall(
                "emotional_history.db",
                "SELECT * FROM emotional_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        for row in rows:
            row["context"] = json.loads(row.pop("context_json") or "{}")
        return rows

    def get_latest_emotion(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        history = self.get_emotional_history(user_id=user_id, limit=1)
        return history[0] if history else None

    def record_provider_call(
        self,
        call_id: str,
        operation: str,
        provider: str,
        latency_ms: float = 0.0,
        success: bool = True,
        error: Optional[str] = None,
        skill: Optional[str] = None,
    ) -> str:
        self.execute(
            "performance_metrics.db",
            """INSERT OR REPLACE INTO provider_calls
               (call_id,operation,provider,latency_ms,success,error,skill,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (call_id, operation, provider, float(latency_ms), 1 if success else 0, error, skill, time.time()),
        )
        return call_id

    def status(self) -> Dict[str, Any]:
        result = {}
        for name in DB_FILES:
            try:
                row = self.fetchone(name, "SELECT value FROM schema_meta WHERE key='schema_version'")
                result[name] = {
                    "available": True,
                    "path": str(self.path(name)),
                    "schema_version": row["value"] if row else None,
                }
            except Exception as exc:
                result[name] = {"available": False, "error": str(exc)}
        return result

    def close(self) -> None:
        conns = getattr(self._local, "connections", {})
        for conn in list(conns.values()):
            try:
                conn.close()
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("database.database_manager.close")
        conns.clear()

    def _initialize_all(self) -> None:
        # The 7 shipped .db files already embed this schema, so on a
        # normal checkout this is a no-op verification pass. But if a
        # .db file is ever deleted, moved, or this runs against a
        # brand-new empty file, CREATE TABLE IF NOT EXISTS here means
        # the store self-heals instead of every write silently failing
        # with "no such table".
        schemas = {
            "world_state.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS world_state_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT NOT NULL UNIQUE,
                    state_json TEXT NOT NULL,
                    source TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_world_state_created_at ON world_state_snapshots(created_at);
            """,
            "goals.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    progress REAL NOT NULL DEFAULT 0.0,
                    parent_goal_id TEXT,
                    metadata_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
                CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal_id);
                CREATE TABLE IF NOT EXISTS goal_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step_id TEXT NOT NULL UNIQUE,
                    goal_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(goal_id) REFERENCES goals(goal_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_goal_steps_goal ON goal_steps(goal_id);
            """,
            "learned_skills.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    description TEXT,
                    workflow_json TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
                CREATE TABLE IF NOT EXISTS skill_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    skill_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    context_json TEXT,
                    result_json TEXT,
                    latency_ms REAL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_skill_runs_skill ON skill_runs(skill_id);
            """,
            "knowledge_graph.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL UNIQUE,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    properties_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
                CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    relation_id TEXT NOT NULL UNIQUE,
                    source_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    properties_json TEXT,
                    valid_from REAL,
                    valid_to REAL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(source_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE,
                    FOREIGN KEY(target_entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_entity_id);
                CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_entity_id);
                CREATE INDEX IF NOT EXISTS idx_rel_type ON relations(relation_type);
            """,
            "confidence_history.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS confidence_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    turn_id TEXT,
                    intent TEXT,
                    confidence REAL,
                    threshold REAL,
                    risk REAL,
                    decision TEXT,
                    context_json TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_confidence_turn ON confidence_events(turn_id);
                CREATE INDEX IF NOT EXISTS idx_confidence_created_at ON confidence_events(created_at);
            """,
            "performance_metrics.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS provider_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL UNIQUE,
                    operation TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    success INTEGER NOT NULL,
                    error TEXT,
                    skill TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_provider_provider ON provider_calls(provider);
                CREATE INDEX IF NOT EXISTS idx_provider_operation ON provider_calls(operation);
                CREATE INDEX IF NOT EXISTS idx_provider_created_at ON provider_calls(created_at);
            """,
            "conversation_history.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    context_json TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation_turns(created_at);
                CREATE INDEX IF NOT EXISTS idx_conversation_role ON conversation_turns(role);
            """,
            "user_profiles.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    preferences_json TEXT,
                    traits_json TEXT,
                    metadata_json TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_user_profiles_updated_at ON user_profiles(updated_at);
            """,
            "emotional_history.db": """
                CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS emotional_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    user_id TEXT,
                    turn_id TEXT,
                    emotion TEXT NOT NULL,
                    intensity REAL,
                    source TEXT,
                    context_json TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_emotional_user ON emotional_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_emotional_turn ON emotional_events(turn_id);
                CREATE INDEX IF NOT EXISTS idx_emotional_created_at ON emotional_events(created_at);
            """,
        }
        for name in DB_FILES:
            conn = self.connection(name)
            conn.executescript(schemas[name])
            conn.commit()


_manager: Optional[DatabaseManager] = None
_manager_lock = threading.Lock()


def get_database_manager() -> DatabaseManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = DatabaseManager()
    return _manager
