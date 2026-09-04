"""Autonomous internet-learning scheduler
==========================================
advanced_engine.py's `research()` method has existed since the Advanced
Autonomy Fabric was added, but nothing ever called it - core/assistant.py
only wired `observe()` and `learn_outcome()` into the per-turn loop, so
research()/create_mission()/checkpoint()/safe_evaluate_evolution() were
dead code with no caller anywhere in the project. This module is the
missing caller for `research()`: a recurring background job, gated behind
ULTRON_LEARN_FROM_INTERNET, that periodically picks one topic and asks
Ultron to actually go look it up.

Topic selection each cycle:
    1. If knowledge_os has a stale fact (see knowledge_os_engine.py's
       get_freshness_report()), re-research that subject first - keeps
       things Ultron already half-knows from silently going out of date.
    2. Otherwise round-robin a curated queue of standing tech/general
       beats (editable at runtime via add_topic()/remove_topic(), and
       persisted to storage/learning/ so a restart doesn't reset it).

Each cycle calls get_advanced_autonomy().research(topic, ai_router=...)
with a *real* AIRouter instance (advanced_engine.py's own research() needs
one to actually synthesize + store a summary - without it, research()
only returns raw unsummarized sources and never writes to knowledge_os).
That call already does the actual web search (skills/web/research.py ->
skills/internet/web_tools.py) and the knowledge_os write
(intelligence/knowledge_os) - this module only supplies the schedule,
the topic, and the ai_router.

Safety: read-only. No new execution path - `research()` was already
callable pre-existing tools (ai/agents_tools.py's research_topic,
ai/new_skills_tools.py's deep_research) without going through
ActionPipeline, since web research isn't a destructive action; this
module doesn't change that. Nothing here writes code or deploys
anything (safe_evaluate_evolution() is untouched, still never auto-
deploys). Halts itself (does not silently keep retrying) after
MAX_CONSECUTIVE_FAILURES so a dead API key or no internet doesn't spin
forever unnoticed - a human has to call start() again after looking.

Built on automation/scheduler/task_scheduler.py, same low-level backend
and start/stop/status/history shape as learning/learning_scheduler.py.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from automation.scheduler.task_scheduler import get_scheduler

logger = get_logger("ultron.autonomous_learning")

DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60  # every 6 hours, same cadence as learning_scheduler.py
MAX_HISTORY = 20
MAX_CONSECUTIVE_FAILURES = 3

STATE_PATH = Path(__file__).resolve().parents[2] / "storage" / "learning" / "autonomous_learning_state.json"

# Curated default beats - broad enough that "seekh kar knowledge upgrade
# kare" covers real ground (tech + general) without the queue going stale.
# Editable at runtime via add_topic()/remove_topic(); persisted to
# STATE_PATH so customization survives a restart.
DEFAULT_TOPICS = [
    "latest large language model releases",
    "Python performance best practices",
    "Windows internals and system programming",
    "cybersecurity threats and defenses",
    "AI agent architectures",
    "robotics and automation news",
    "open source developer tools",
    "computer vision techniques",
    "cloud infrastructure trends",
    "general science breakthroughs",
]


class AutonomousLearningScheduler:
    """Runs get_advanced_autonomy().research() on a recurring interval,
    one topic per cycle, sourced from knowledge_os's stale facts first
    and a curated tech/general queue otherwise."""

    def __init__(self):
        self._backend = get_scheduler()
        self._task_id: Optional[str] = None
        self._history: List[Dict] = []
        self._consecutive_failures = 0
        self._ai_router = None
        self._state = self._load_state()

    # -- state (topic queue + cursor) ---------------------------------
    def _load_state(self) -> Dict:
        try:
            if STATE_PATH.exists():
                loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                loaded.setdefault("topics", list(DEFAULT_TOPICS))
                loaded.setdefault("cursor", 0)
                return loaded
        except Exception:
            logger.exception("autonomous_learning: state load failed, starting fresh")
        return {"topics": list(DEFAULT_TOPICS), "cursor": 0}

    def _save_state(self) -> None:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("autonomous_learning: state save failed")

    def add_topic(self, topic: str) -> Dict:
        topic = (topic or "").strip()
        if topic and topic not in self._state["topics"]:
            self._state["topics"].append(topic)
            self._save_state()
        return {"success": True, "topics": self._state["topics"]}

    def remove_topic(self, topic: str) -> Dict:
        topic = (topic or "").strip().lower()
        self._state["topics"] = [t for t in self._state["topics"] if t.lower() != topic]
        self._state["cursor"] = 0
        self._save_state()
        return {"success": True, "topics": self._state["topics"]}

    def _next_topic(self) -> str:
        """Prioritize a stale knowledge_os fact if one exists, else
        round-robin the curated queue."""
        try:
            from intelligence.knowledge_os import get_knowledge_os

            report = get_knowledge_os().get_freshness_report()
            stale_facts = report.get("stale_facts") or []
            if stale_facts:
                return stale_facts[0]["subject"]
        except Exception:
            logger.exception("autonomous_learning: stale-fact lookup failed, falling back to curated queue")

        topics = self._state.get("topics") or DEFAULT_TOPICS
        cursor = self._state.get("cursor", 0) % len(topics)
        topic = topics[cursor]
        self._state["cursor"] = (cursor + 1) % len(topics)
        self._save_state()
        return topic

    def _get_ai_router(self):
        """Lazy singleton - imported here, not at module load time, for
        the same circular-import reason advanced_engine.py's research()
        takes ai_router as an injected argument rather than importing it
        itself."""
        if self._ai_router is None:
            from ai.ai_router import AIRouter

            self._ai_router = AIRouter()
        return self._ai_router

    # -- cycle ----------------------------------------------------------
    def run_once(self, topic: Optional[str] = None) -> Dict:
        """Run one research cycle. Safe to call directly (e.g. from a
        tool, for an on-demand 'ise abhi ye seekhne do') without start()."""
        from intelligence.ultron_advanced import get_advanced_autonomy

        started = time.time()
        chosen = topic or self._next_topic()
        result: Dict = {"topic": chosen, "started_at": started}
        try:
            research_result = get_advanced_autonomy().research(chosen, ai_router=self._get_ai_router())
            result["success"] = bool(research_result.get("success"))
            result["sources_read"] = research_result.get("sources_read", 0)
            result["stored_in_knowledge_os"] = research_result.get("stored_in_knowledge_os", False)
            if not result["success"]:
                result["error"] = research_result.get("error")
        except Exception as e:
            logger.error(f"autonomous_learning cycle failed for '{chosen}': {e}")
            result["success"] = False
            result["error"] = str(e)
        result["ended_at"] = time.time()
        result["duration_seconds"] = round(result["ended_at"] - started, 3)

        if result["success"]:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES and self._task_id is not None:
                logger.warning(
                    f"autonomous_learning: {self._consecutive_failures} consecutive failures - "
                    "pausing the recurring schedule until a human calls start() again."
                )
                self.stop()

        self._history.append(result)
        self._history = self._history[-MAX_HISTORY:]
        logger.info(
            f"autonomous_learning cycle for '{chosen}' finished in "
            f"{result['duration_seconds']}s (success={result['success']})"
        )
        return result

    def start(self, interval_seconds: float = DEFAULT_INTERVAL_SECONDS) -> Dict:
        """Begin running run_once() every `interval_seconds`. No-op if
        already running - call stop() first to change the interval."""
        if self._task_id is not None:
            return {"error": "Autonomous learning scheduler already running", "task_id": self._task_id}
        self._task_id = self._backend.run_every(interval_seconds, self.run_once)
        self._consecutive_failures = 0
        logger.info(f"autonomous_learning scheduler started, interval={interval_seconds}s")
        return {"success": True, "task_id": self._task_id, "interval_seconds": interval_seconds}

    def stop(self) -> Dict:
        if self._task_id is None:
            return {"error": "Autonomous learning scheduler is not running"}
        cancelled = self._backend.cancel(self._task_id)
        self._task_id = None
        return {"success": cancelled}

    def status(self) -> Dict:
        return {
            "running": self._task_id is not None,
            "task_id": self._task_id,
            "topics_queued": len(self._state.get("topics") or []),
            "cursor": self._state.get("cursor", 0),
            "consecutive_failures": self._consecutive_failures,
            "cycles_run": len(self._history),
            "last_cycle": self._history[-1] if self._history else None,
        }

    def history(self, limit: int = MAX_HISTORY) -> Dict:
        entries = self._history[-limit:][::-1]
        return {"count": len(entries), "entries": entries}


_autonomous_learning_scheduler: Optional[AutonomousLearningScheduler] = None


def get_autonomous_learning_scheduler() -> AutonomousLearningScheduler:
    global _autonomous_learning_scheduler
    if _autonomous_learning_scheduler is None:
        _autonomous_learning_scheduler = AutonomousLearningScheduler()
    return _autonomous_learning_scheduler
