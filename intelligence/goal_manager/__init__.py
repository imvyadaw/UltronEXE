"""
Goal Manager (Phase 19.3)
=============================
Full lifecycle manager for goals, built directly on top of Phase
19.1's intelligence.world_state and interoperable with Phase 19.2's
intelligence.intent_prediction - backed by a single shared database
at database/goals.db:

    goal_store.py       - sqlite CRUD for goals, ordered steps, and
                           an append-only event log
    goal_decomposer.py  - rule-based title/description -> ordered
                           list of steps
    progress_tracker.py - per-goal completion %, marks steps done/
                           skipped, auto-completes finished goals
    pause_resume.py     - active <-> paused lifecycle transitions
    recovery_manager.py - flags stalled active goals and suggests a
                           next concrete step to get them moving
    goal_manager.py      - single entry point tying all of the above
                           together

Usage:
    from intelligence.goal_manager import get_goal_manager
    gm = get_goal_manager()
    goal = gm.create_goal("Learn FastAPI", priority="high")
    gm.advance_step(goal["steps"][0]["id"])
    gm.pause_goal(goal["id"], reason="switched priorities")
    gm.resume_goal(goal["id"])
    gm.recovery_report(threshold_days=7)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through the top-level manager.

Purely additive - nothing in Phase 1-19.2 imports from here.
"""

from intelligence.goal_manager.goal_store import GoalStore, get_goal_store
from intelligence.goal_manager.goal_decomposer import GoalDecomposer, get_goal_decomposer
from intelligence.goal_manager.progress_tracker import ProgressTracker, get_progress_tracker
from intelligence.goal_manager.pause_resume import PauseResumeManager, get_pause_resume_manager
from intelligence.goal_manager.recovery_manager import RecoveryManager, get_recovery_manager
from intelligence.goal_manager.goal_manager import GoalManager, get_goal_manager

__all__ = [
    "GoalManager",
    "get_goal_manager",
    "GoalStore",
    "get_goal_store",
    "GoalDecomposer",
    "get_goal_decomposer",
    "ProgressTracker",
    "get_progress_tracker",
    "PauseResumeManager",
    "get_pause_resume_manager",
    "RecoveryManager",
    "get_recovery_manager",
]
