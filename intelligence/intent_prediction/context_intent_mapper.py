"""
Context Intent Mapper (Phase 19.2 - Intent Prediction)
=========================================================
Turns a context snapshot - active app, time of day, whether a task is
in flight - into ranked candidate intents. Two signal sources are
blended: a small set of builtin heuristic rules (e.g. an IDE in focus
suggests "coding"), and learned associations built from whatever this
process has observed via record_observation(), which just counts how
often a given context key has co-occurred with a given intent label.

When no context is passed in, map_context() pulls the live picture
from intelligence.world_state (Phase 19.1) - active_context.current(),
environment_state.get_time_context(), and whether task_state has
anything active - rather than requiring every caller to assemble that
themselves.

Storage: database/intent_prediction.db, table context_observations.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "intent_prediction.db"

# app-name substring (lowercased) -> (intent, base_score)
BUILTIN_APP_RULES = {
    "code": ("coding", 0.7),
    "vscode": ("coding", 0.7),
    "pycharm": ("coding", 0.7),
    "terminal": ("coding", 0.5),
    "github": ("coding", 0.55),
    "chrome": ("browsing", 0.4),
    "firefox": ("browsing", 0.4),
    "edge": ("browsing", 0.4),
    "outlook": ("communicating", 0.6),
    "gmail": ("communicating", 0.6),
    "slack": ("communicating", 0.6),
    "teams": ("communicating", 0.6),
    "discord": ("communicating", 0.5),
    "spotify": ("relaxing", 0.5),
    "netflix": ("relaxing", 0.6),
    "youtube": ("relaxing", 0.45),
    "excel": ("working_docs", 0.6),
    "word": ("working_docs", 0.6),
    "powerpoint": ("working_docs", 0.6),
    "notion": ("planning", 0.55),
    "obsidian": ("planning", 0.55),
    "calendar": ("planning", 0.6),
}

# time_of_day -> (intent, base_score) - weak prior, only nudges the ranking
BUILTIN_TIME_RULES = {
    "morning": [("planning", 0.2), ("coding", 0.1)],
    "afternoon": [("coding", 0.15), ("working_docs", 0.1)],
    "evening": [("relaxing", 0.2), ("communicating", 0.1)],
    "night": [("relaxing", 0.25)],
}

_instance: Optional["ContextIntentMapper"] = None
_instance_lock = threading.Lock()


class ContextIntentMapper:
    """Maps context signals to ranked candidate intents, blending builtin
    heuristics with learned observation counts."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS context_observations (
                context_key TEXT,
                intent TEXT,
                count INTEGER,
                updated_at REAL,
                PRIMARY KEY (context_key, intent)
            )""")
        self._conn.commit()

    # -- context normalization ------------------------------------------------
    @staticmethod
    def _context_keys(context: Dict) -> List[str]:
        """Break a context dict into normalized "facet:value" keys."""
        keys = []
        app = (context.get("active_app") or "").lower()
        if app:
            keys.append(f"app:{app}")
        window = (context.get("window_title") or "").lower()
        if window:
            keys.append(f"window:{window}")
        time_of_day = context.get("time_of_day")
        if time_of_day:
            keys.append(f"time:{time_of_day}")
        day = context.get("day_of_week")
        if day:
            keys.append(f"day:{day}")
        if context.get("has_active_task"):
            keys.append("task:active")
        return keys

    # -- learning ---------------------------------------------------------------
    def record_observation(self, context: Dict, intent: str) -> Dict:
        """Record that `intent` co-occurred with this context, incrementing
        the count for each normalized context key derived from it."""
        if not intent:
            return {"error": "intent required"}
        keys = self._context_keys(context)
        now = time.time()
        with self._lock:
            for key in keys:
                self._conn.execute(
                    """INSERT INTO context_observations (context_key, intent, count, updated_at)
                       VALUES (?, ?, 1, ?)
                       ON CONFLICT(context_key, intent) DO UPDATE SET
                           count = count + 1, updated_at = excluded.updated_at""",
                    (key, intent, now),
                )
            self._conn.commit()
        return {"success": True, "keys": keys}

    def _score_learned(self, context: Dict) -> Dict[str, float]:
        keys = self._context_keys(context)
        if not keys:
            return {}
        totals: Dict[str, float] = {}
        with self._lock:
            for key in keys:
                cur = self._conn.execute("SELECT intent, count FROM context_observations WHERE context_key = ?", (key,))
                rows = cur.fetchall()
                key_total = sum(r[1] for r in rows) or 1
                for intent, count in rows:
                    totals[intent] = totals.get(intent, 0.0) + (count / key_total)
        if not totals:
            return {}
        max_score = max(totals.values()) or 1.0
        return {intent: score / max_score for intent, score in totals.items()}

    # -- builtin heuristics -----------------------------------------------------
    def _score_builtin(self, context: Dict) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        app = (context.get("active_app") or "").lower()
        for needle, (intent, base_score) in BUILTIN_APP_RULES.items():
            if needle in app:
                scores[intent] = max(scores.get(intent, 0.0), base_score)
        time_of_day = context.get("time_of_day")
        for intent, base_score in BUILTIN_TIME_RULES.get(time_of_day, []):
            scores[intent] = max(scores.get(intent, 0.0), base_score)
        return scores

    # -- public entry point -------------------------------------------------------
    def map_context(self, context: Optional[Dict] = None) -> List[Dict]:
        """Rank candidate intents for a given context. If `context` isn't
        given, pulls the live picture from intelligence.world_state
        (active app/window, time of day, whether a task is active)."""
        if context is None:
            context = self.live_context()

        builtin_scores = self._score_builtin(context)
        learned_scores = self._score_learned(context)

        intents = set(builtin_scores) | set(learned_scores)
        ranked = []
        for intent in intents:
            # builtin heuristics anchor the score; learned observations nudge it
            score = (builtin_scores.get(intent, 0.0) * 0.6) + (learned_scores.get(intent, 0.0) * 0.4)
            ranked.append({"intent": intent, "score": round(score, 4)})
        ranked.sort(key=lambda r: r["score"], reverse=True)
        return ranked

    @staticmethod
    def live_context() -> Dict:
        """Best-effort pull of a context dict from Phase 19.1's world_state.
        Any piece that fails to load is simply omitted rather than raising."""
        context: Dict = {}
        try:
            from intelligence.world_state.active_context import get_active_context

            active = get_active_context().current()
            context["active_app"] = active.get("active_app")
            context["window_title"] = active.get("window_title")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("intelligence.intent_prediction.context_intent_mapper.live_context")
        try:
            from intelligence.world_state.environment_state import get_environment_state

            time_ctx = get_environment_state().get_time_context()
            context["time_of_day"] = time_ctx.get("time_of_day")
            context["day_of_week"] = time_ctx.get("day_of_week")
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("intelligence.intent_prediction.context_intent_mapper.live_context")
        try:
            from intelligence.world_state.task_state import get_task_state

            context["has_active_task"] = len(get_task_state().active_tasks()) > 0
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("intelligence.intent_prediction.context_intent_mapper.live_context")
        return context


def get_context_intent_mapper() -> ContextIntentMapper:
    """Process-wide ContextIntentMapper singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ContextIntentMapper()
    return _instance
