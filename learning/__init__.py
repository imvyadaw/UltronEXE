"""Learning package
=================
Two layers, built in sequence (Phase 4.1 then 4.2-4.5), that share the
learning/ namespace but answer different questions:

  - Phase 4.1 (learner.py, experience.py): "how much should Ultron
    trust re-running this exact action unattended?" - grades Ultron's
    own action outcomes (via core.event_bus's action.completed/
    action.failed events) into a per-action confidence score.
    safety/trust_policy.py and safety/action_approval.py are the
    normal callers of the read side.
        from learning.learner import get_learner
        from learning.experience import get_experience_store

  - Phase 4.2-4.5 (knowledge_extractor.py, source_validator.py,
    confidence.py, pattern_detector.py, skill_learner.py,
    failure_learner.py, memory_consolidator.py, forgetting.py,
    learning_scheduler.py): turns conversation/observed text into
    knowledge_base/ facts, and recurring successful episodes into
    memory/procedural/ + intelligence/skill_builder/ skills - gated,
    for anything that would grant new autonomy, by safety/policy.py +
    safety/review_queue.py. learning_scheduler.get_learning_scheduler()
    is that layer's own front door (run_once() runs the whole
    consolidate/scan/promote/forget cycle); each submodule also works
    standalone for a caller that only needs one piece.

Consumers should import the singleton getters, not the classes.
"""

from learning.experience import get_experience_store, ExperienceStore
from learning.learner import get_learner, Learner

__all__ = [
    "get_experience_store",
    "ExperienceStore",
    "get_learner",
    "Learner",
]
