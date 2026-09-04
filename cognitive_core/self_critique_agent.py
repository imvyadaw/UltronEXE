"""
Self-critique agent
====================
New capability - nothing in Phase 1-16 checks its own work. Every
existing planner/workflow runner treats "all steps returned success"
as done. That's often wrong: a step can succeed (e.g. "search Downloads
for old files" returns an empty list successfully) without the goal
actually being met.

This agent takes the goal plus a core.workflow_engine-shaped execution
report (the dict run_ad_hoc()/run_workflow() already return) and asks
the LLM, in one extra round-trip, whether the goal reads as achieved.
Used by autonomous_executor.py to decide whether to stop, or to hand
the "reason"/"suggested_fix" back to goal_planner.plan_goal() as
`feedback` for a bounded re-attempt.

Fails closed toward *not* blocking the pipeline: if the LLM call errors
or returns something unparseable, this falls back to a plain structural
check (did every step report success?) instead of raising - a broken
critique call should degrade to "trust the step results", never halt
an otherwise-working run.
"""

import json
from typing import Dict, Optional

from ai.ai_router import get_router

CRITIQUE_PROMPT = """A goal was attempted and here is what happened. Judge honestly whether \
the goal was actually achieved - a step "succeeding" technically doesn't always mean the \
goal was met (e.g. a search that ran fine but found nothing useful).

Respond with ONLY a JSON object, nothing else - no prose, no markdown fences:
{{"satisfied": true or false, "reason": "one sentence", "suggested_fix": "one sentence or empty string"}}

Goal: {goal}

Execution report (steps and their results):
{report}"""

MAX_REPORT_CHARS = 4000


class SelfCritiqueAgent:
    def critique(self, goal: str, execution_report: Dict) -> Dict:
        """Returns {"satisfied": bool, "reason": str, "suggested_fix": str,
        "source": "llm" | "fallback"}. Never raises."""
        report_text = json.dumps(execution_report, default=str)[:MAX_REPORT_CHARS]
        text = ""
        try:
            prompt = CRITIQUE_PROMPT.format(goal=goal, report=report_text)
            text = get_router().complete(prompt, temperature=0.1, max_tokens=250)
            text = text.strip().strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()

            parsed = json.loads(text)
            if not isinstance(parsed, dict) or "satisfied" not in parsed:
                return self._structural_fallback(execution_report)

            return {
                "satisfied": bool(parsed["satisfied"]),
                "reason": str(parsed.get("reason", "")).strip(),
                "suggested_fix": str(parsed.get("suggested_fix", "")).strip(),
                "source": "llm",
            }
        except json.JSONDecodeError:
            return self._structural_fallback(execution_report)
        except Exception:
            return self._structural_fallback(execution_report)

    def _structural_fallback(self, execution_report: Dict) -> Dict:
        """No LLM opinion available - fall back to "did every step
        report success" as a conservative proxy. Never claims a fix is
        needed it can't actually describe."""
        steps = execution_report.get("steps", []) if isinstance(execution_report, dict) else []
        all_ok = bool(steps) and all(s.get("success", False) or s.get("skipped", False) for s in steps)
        failed = [
            s.get("label", s.get("tool", "?"))
            for s in steps
            if not (s.get("success", False) or s.get("skipped", False))
        ]
        return {
            "satisfied": all_ok,
            "reason": "All steps reported success." if all_ok else f"Step(s) failed: {', '.join(failed) or 'unknown'}",
            "suggested_fix": "",
            "source": "fallback",
        }


_agent: Optional[SelfCritiqueAgent] = None


def get_self_critique_agent() -> SelfCritiqueAgent:
    global _agent
    if _agent is None:
        _agent = SelfCritiqueAgent()
    return _agent
