"""
Failure Diagnoser (Phase 19.5 - Self Healing)
=================================================
Turns a raw failure - a caught exception, an error string, and/or a
Phase 19.4 verification_engine result - into a structured diagnosis:
a category (timeout, missing_resource, permission, network,
verification_failed, unknown), the specific check(s) that failed if
any, and a stable signature string. That signature is the join key
healing_memory.py uses to remember "last time this exact kind of
failure happened, X fixed it" - so it has to be based only on stable
facts (action name + category + normalized keywords), never on
anything that changes run to run like a timestamp or a full stack
trace.
"""

import hashlib
import re
import threading
from typing import Dict, List, Optional, Tuple

_instance: Optional["FailureDiagnoser"] = None
_instance_lock = threading.Lock()

# ordered (category, pattern) - checked in order, first match wins.
# Applied to the lowercased error message / exception text.
_ERROR_PATTERNS = [
    ("timeout", r"timed?\s*out|timeout|deadline exceeded"),
    ("missing_resource", r"no such file|not found|does not exist|missing|enoent|404"),
    ("permission", r"permission denied|access is denied|forbidden|401|403|not authorized"),
    ("network", r"connection refused|network|dns|unreachable|econnreset|ssl|socket"),
    ("resource_exhausted", r"out of memory|disk full|no space left|too many open files|rate limit"),
]

# verification_engine check "type"/"check" names -> diagnosis category
_CHECK_TYPE_CATEGORY = {
    "file_exists": "missing_resource",
    "file_not_empty": "missing_resource",
    "file_modified_after": "stale_result",
    "file_contains": "unexpected_content",
    "file_hash_matches": "unexpected_content",
    "screenshot_changed": "no_visible_effect",
    "screenshot_matches_baseline": "unexpected_state",
    "result": "unexpected_result",
}


class FailureDiagnoser:
    """Classifies a failure and produces a stable signature for it."""

    def diagnose(
        self,
        action_name: str,
        error: Optional[str] = None,
        verification_result: Optional[Dict] = None,
    ) -> Dict:
        """error can be an exception instance or a plain string message.
        verification_result is the dict returned by
        verification_engine.verify()/verify_action() - its failed
        checks (if any) are folded into the diagnosis too."""
        error_text = str(error) if error is not None else ""
        category, matched_keyword = self._classify_error_text(error_text)

        failed_checks: List[Dict] = []
        if verification_result:
            for r in verification_result.get("results", []) or verification_result.get("checks", []):
                if not r.get("passed"):
                    failed_checks.append(r)
            if category == "unknown" and failed_checks:
                check_name = failed_checks[0].get("check") or failed_checks[0].get("type")
                category = _CHECK_TYPE_CATEGORY.get(check_name, "verification_failed")

        signature = self._build_signature(action_name, category, error_text, failed_checks)

        return {
            "action_name": action_name,
            "category": category,
            "matched_keyword": matched_keyword,
            "error_text": error_text,
            "failed_checks": failed_checks,
            "signature": signature,
            "historical_caution": self._historical_caution(action_name),
        }

    @staticmethod
    def _historical_caution(action_name: str) -> Optional[Dict]:
        """learning/failure_learner.py's should_caution() for this
        action_name, if it has already crossed a failure-rate threshold as
        a 'tool' subject over its structured success/failure history
        (memory/history/tracker.py). This diagnoser only ever sees one
        failure at a time; folding in that module's aggregated view lets
        healing_memory.py's "last time this exact signature happened, X
        fixed it" sit alongside "and this tool has a track record of
        failing generally" without the two modules needing to know about
        each other beyond this one lookup. None (not an empty dict) when
        failure_learner.py isn't available or has no lesson on file, so a
        caller can tell "no signal" apart from "checked, no caution"."""
        try:
            from learning.failure_learner import get_failure_learner

            verdict = get_failure_learner().should_caution(action_name, subject_type="tool")
            return verdict if verdict.get("caution") else None
        except Exception:
            return None

    @staticmethod
    def _classify_error_text(error_text: str) -> Tuple[str, Optional[str]]:
        if not error_text:
            return "unknown", None
        lowered = error_text.lower()
        for category, pattern in _ERROR_PATTERNS:
            match = re.search(pattern, lowered)
            if match:
                return category, match.group(0)
        return "unknown", None

    @staticmethod
    def _build_signature(action_name: str, category: str, error_text: str, failed_checks: List[Dict]) -> str:
        check_names = ",".join(sorted({c.get("check") or c.get("type") or "" for c in failed_checks}))
        # strip anything that looks like a number/path/timestamp so the
        # signature stays stable across repeats of the "same" failure
        normalized_error = re.sub(r"[0-9]+", "#", error_text.lower())[:120]
        raw = f"{action_name}|{category}|{check_names}|{normalized_error}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_failure_diagnoser() -> FailureDiagnoser:
    """Process-wide FailureDiagnoser singleton (stateless, but shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = FailureDiagnoser()
    return _instance
