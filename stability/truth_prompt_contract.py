"""
Truth prompt contract
======================
`ai/prompts/system_prompts.py`'s SYSTEM_PROMPT is thorough about *when* to
call a tool (see "CRITICAL: WHEN TO USE TOOLS vs JUST TALK") but says
nothing about what to do with a tool's *result* once it comes back - there
was no explicit instruction against the one failure mode that matters most
for an agent that actually controls the user's PC: reporting a tool call as
having succeeded (or a fact as verified) when the tool result it just
received says otherwise, or describes doing something no tool was ever
called to do at all ("I've sent the email" with no send_email call in this
turn). That's a plausible, previously-undocumented gap, not a bug someone
filed - hence "new addition" here rather than "found and fixed".

Two halves, same "degrade, don't crash" pattern as the rest of Phase 29/29-A:

1. TRUTH_CONTRACT_ADDENDUM - a system-prompt section instructing the model
   never to assert an action succeeded except on a tool result that says so,
   and to say "I attempted X but it failed: <reason>" rather than staying
   silent about a failure or reporting it as a success anyway.
2. check_turn() - a cheap, best-effort *runtime* heuristic (regex over the
   final response text, not an LLM call) that flags likely violations for
   logging/QA. It is deliberately advisory, not a blocker: false positives
   are possible (this is pattern matching, not language understanding), so
   it reports, it doesn't rewrite or withhold the response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    from core.logger import get_logger

    _logger = get_logger("ultron.stability.truth_contract")
except Exception:  # pragma: no cover
    import logging

    _logger = logging.getLogger("ultron.stability.truth_contract")


TRUTH_CONTRACT_ADDENDUM = """
=== TRUTH CONTRACT (tool results) ===

Once a tool call returns, its result is the only source of truth for
whether that action happened - not what you intended to happen, not what
usually happens, not the user's phrasing of the request.

- Never describe an action as done, sent, opened, saved, created, deleted,
  or otherwise completed unless a tool call in this turn actually returned
  success for it.
- If a tool result contains an error, say so plainly and specifically (what
  failed and, if the result gives one, why) - do not report it as a success,
  and do not silently drop the failure and move on as if nothing happened.
- Never state a fact as tool-verified (a current price, score, status,
  search result) unless a tool call actually returned that fact this turn.
  If you're speaking from general knowledge instead, that's fine - just
  don't imply a lookup happened when it didn't.
- If a multi-step chain partially fails (e.g. open_application succeeded
  but the following type_text failed), report exactly which step failed
  and which succeeded - not a blanket "done" or a blanket "failed".
"""


_CLAIM_PATTERNS = [
    # (regex, human label) - present/past-tense first-person completion claims.
    (re.compile(r"\bi(?:'ve| have)?\s+(?:just\s+)?(opened|launched|started)\b", re.I), "opened/launched"),
    (re.compile(r"\bi(?:'ve| have)?\s+(?:just\s+)?(sent|emailed)\b", re.I), "sent"),
    (re.compile(r"\bi(?:'ve| have)?\s+(?:just\s+)?(saved|written|created|made)\b", re.I), "saved/created"),
    (re.compile(r"\bi(?:'ve| have)?\s+(?:just\s+)?(deleted|removed|closed)\b", re.I), "deleted/closed"),
    (re.compile(r"\bi(?:'ve| have)?\s+(?:just\s+)?(set|changed|updated)\b", re.I), "set/changed"),
    (re.compile(r"\b(done|all set|task complete|completed successfully)\b", re.I), "generic completion"),
]


@dataclass
class TruthCheckResult:
    ok: bool
    suspected_claims: List[str] = field(default_factory=list)
    tool_errors_unmentioned: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "truth contract: no issues detected"
        parts = []
        if self.suspected_claims:
            parts.append(f"completion language with no matching successful tool call: {self.suspected_claims}")
        if self.tool_errors_unmentioned:
            parts.append(f"tool error(s) not reflected in the response text: {self.tool_errors_unmentioned}")
        return "truth contract: " + "; ".join(parts)


def check_turn(
    response_text: str,
    tool_calls: Optional[List[str]] = None,
    tool_results: Optional[List[Dict]] = None,
) -> TruthCheckResult:
    """Best-effort, non-blocking check of one turn's final response against
    what tools actually reported this turn.

    tool_calls: names of tools invoked this turn (may be empty).
    tool_results: the corresponding result dicts, expected to look like
    core/error_handler.py's `{"success": bool, ...}` shape where available,
    but tolerant of the older `{"error": ...}` / no-key shape too.
    """
    tool_calls = tool_calls or []
    tool_results = tool_results or []

    any_successful_tool_call = any((isinstance(r, dict) and r.get("success", "error" not in r)) for r in tool_results)
    suspected = []
    if not tool_calls or not any_successful_tool_call:
        for pattern, label in _CLAIM_PATTERNS:
            if pattern.search(response_text or ""):
                suspected.append(label)

    unmentioned_errors = []
    for r in tool_results:
        if not isinstance(r, dict):
            continue
        err = r.get("error")
        if err and str(err)[:24].lower() not in (response_text or "").lower():
            # Very loose "did the response even gesture at this error"
            # check - a short prefix of the error text appearing anywhere.
            unmentioned_errors.append(str(err))

    result = TruthCheckResult(
        ok=not suspected and not unmentioned_errors,
        suspected_claims=suspected,
        tool_errors_unmentioned=unmentioned_errors,
    )
    if not result.ok:
        _logger.warning(result.summary())
    return result
