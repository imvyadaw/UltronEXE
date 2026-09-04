"""Safety (Phase 4.5)
==================
learning/'s own docstrings are explicit that Phase 4.2-4.4 never gates
anything on human review: pattern_detector.py "only ever reinforces or
creates", failure_learner.py "only ever flags a caution... never blocks
an action", and until this phase skill_learner.py's promote_masters()
would flip a procedure straight to skill_builder's STATUS_ACTIVE the
moment it crossed the mastery thresholds - fully autonomous adoption of
a *newly invented* behavior, whatever that behavior happens to be.

That's a fine default for anything low-stakes, but "delete the stale
downloads" and "wire a payment" shouldn't earn the same trust just
because both happened to succeed enough times. This package is the
higher-level caller learning/'s docstrings kept pointing at and never
built: it doesn't touch pattern detection, failure flagging, or decay -
it sits specifically in front of skill_learner.py's promotion step and
learning_scheduler.py's recurring cycle.

    - policy.py classifies a procedure by keyword-heuristic risk
      (destructive / financial / outbound-communication / system-security),
      the same "fast heuristic, not a guarantee" spirit as
      learning/source_validator.py's domain trust tiers, with the same
      kind of manual-override escape hatch, persisted separately per name.
    - review_queue.py holds anything policy.py flags, pending a human
      approve()/reject() - a plain JSON queue, same storage trade-off as
      learning/failure_learner.py's lessons file and learning/forgetting.py's
      prune log (a handful of promotions a week, easy to audit by hand).
    - guardian.py watches learning_scheduler.py's own cycle results for
      signs a cycle went wrong in a way severity alone won't catch - a
      prune-fraction spike, or several failed cycles in a row - and tells
      the scheduler to stop its recurring run rather than trusting every
      future cycle to also be fine.

Nothing here touches confidence scoring, pattern detection, or decay
math - see learning/confidence.py, learning/pattern_detector.py,
learning/forgetting.py for that. This package only ever adds a stop; it
never adds new autonomy of its own.

Four more modules extend that same "only ever adds a stop" spirit to
things outside skill promotion:

    - learning_policy.py is policy.py under the name learning/'s own
      docstrings point callers toward - same object, not a second
      implementation.
    - trust_policy.py answers "how much do we trust *where this came
      from*" (learning/source_validator.py + learning/confidence.py),
      as distinct from policy.py's "is this *content* risky".
    - action_approval.py extends policy.py/review_queue.py's gate from
      "should this procedure become a trusted skill" to "should this
      *specific destructive tool call* run right now with nobody
      present to confirm it" - core/permissions.py's PermissionGate
      already knows which tools are destructive; this is what asks a
      human before an unattended one runs.
Alongside that (Phase 4.5, gating *skill promotion*), this package also
holds Phase 4.1's four modules, gating *unattended re-execution of an
already-known action* instead:

    - learning_policy.py: which actions may even have their outcomes
      folded into a trust score (core.permissions.PermissionGate's
      DESTRUCTIVE_TOOLS are excluded here by default - a good streak
      should never quietly erode "always confirm this").
    - trust_policy.py: turns learning/learner.py's per-action
      confidence into ASK_EVERY_TIME / SUGGEST_ONLY / AUTO_EXECUTE.
    - action_approval.py: the single call site other packages use to
      ask "can this run unattended right now" - wraps trust_policy.py
      with context overrides (e.g. force-ask during a live call) and
      routes newly-trusted actions through sandbox.py first.
    - sandbox.py: supervised trial runs (real tool, timeout + capture,
      result reported back into learner.py) for a fixed number of
      runs before action_approval.py stops routing an action through
      here at all. Distinct from skill_creator/sandbox_tester.py and
      ultron_shield/sandbox_executor.py's process-isolation flavour of
      "sandbox" - see this module's own docstring.

Phase 4.5 (policy.py/review_queue.py/guardian.py) and Phase 4.1
(learning_policy.py/trust_policy.py/action_approval.py/sandbox.py)
gate different things and don't call into each other; both are
exported from here so a caller never needs to know which phase built
which check.
"""

from safety.policy import get_safety_policy, TIER_AUTO, TIER_REVIEW
from safety.review_queue import get_review_queue, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED
from safety.guardian import get_learning_guardian
from safety.learning_policy import get_learning_policy, LearningPolicy
from safety.trust_policy import get_trust_policy, TrustPolicy, TrustLevel
from safety.action_approval import get_action_approval_gate, ActionApprovalGate, ApprovalDecision
from safety.sandbox import get_sandbox_executor, SandboxExecutor

__all__ = [
    "get_safety_policy",
    "TIER_AUTO",
    "TIER_REVIEW",
    "get_review_queue",
    "STATUS_PENDING",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    "get_learning_guardian",
    "get_learning_policy",
    "LearningPolicy",
    "get_trust_policy",
    "TrustPolicy",
    "TrustLevel",
    "get_action_approval_gate",
    "ActionApprovalGate",
    "ApprovalDecision",
    "get_sandbox_executor",
    "SandboxExecutor",
]
