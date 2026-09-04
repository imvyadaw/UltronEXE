"""
Skill Builder (Phase 19.6)
=============================
Turns what ULTRON actually does into reusable skills: watches for
deliberate walkthroughs or action sequences that keep repeating on
their own, generalizes them into a template of fixed values vs
variable placeholders, and stores the result as a runnable skill
that gets promoted or deprecated based on how well it actually
works - all backed by a shared database at
database/learned_skills.db:

    workflow_recorder.py   - logs every action; groups an explicit
                              walkthrough into a named session
    workflow_detector.py   - finds action sequences repeating in the
                              ambient history, unprompted
    workflow_analyzer.py   - generalizes one or more instances of a
                              sequence into fixed vs {{placeholder}} params
    skill_generator.py     - builds a name + description + steps
                              skill definition from an analysis
    skill_store.py         - persists skills, tracks usage stats,
                              promotes/deprecates on each recorded run
    skill_improver.py      - turns a skill's stats into promote /
                              deprecate / stale / duplicate calls
    skill_builder_engine.py - single entry point tying all of the
                              above together

Usage:
    from intelligence.skill_builder import get_skill_builder_engine
    sb = get_skill_builder_engine()

    # explicit - record a walkthrough, then build a skill from it
    sid = sb.start_recording("morning_report")
    sb.record_step("open_email", {"folder": "inbox"}, session_id=sid)
    sb.record_step("summarize", {"count": 10}, session_id=sid)
    result = sb.stop_recording_and_build(sid)

    # implicit - mine the ambient history for repeating sequences
    new_skills = sb.detect_from_history()

    # advisory mode - just get the resolved plan, don't execute anything
    plan = sb.run_skill(result["skill_id"])

    # active mode - actually run it
    def executor(action_name, params):
        ...  # perform action_name(**params), return True/False
    outcome = sb.run_skill(result["skill_id"], executor=executor)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through the top-level engine.

Purely additive - nothing in Phase 1-19.5 imports from here.
"""

from intelligence.skill_builder.workflow_recorder import WorkflowRecorder, get_workflow_recorder
from intelligence.skill_builder.workflow_detector import WorkflowDetector, get_workflow_detector
from intelligence.skill_builder.workflow_analyzer import WorkflowAnalyzer, get_workflow_analyzer
from intelligence.skill_builder.skill_generator import SkillGenerator, get_skill_generator
from intelligence.skill_builder.skill_store import SkillStore, get_skill_store
from intelligence.skill_builder.skill_improver import SkillImprover, get_skill_improver
from intelligence.skill_builder.skill_builder_engine import SkillBuilderEngine, get_skill_builder_engine

__all__ = [
    "SkillBuilderEngine",
    "get_skill_builder_engine",
    "WorkflowRecorder",
    "get_workflow_recorder",
    "WorkflowDetector",
    "get_workflow_detector",
    "WorkflowAnalyzer",
    "get_workflow_analyzer",
    "SkillGenerator",
    "get_skill_generator",
    "SkillStore",
    "get_skill_store",
    "SkillImprover",
    "get_skill_improver",
]
