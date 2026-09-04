"""
Success Evaluator (Phase 19.4 - Verification)
=================================================
Takes a flat list of heterogeneous checks - some about files, some
about screenshots, some about a plain result value - dispatches each
to the right verifier (file_verifier / screenshot_verifier /
result_verifier), and rolls them all up into one score and pass/
fail. This is the module that answers "overall, did the thing
actually succeed", given a list of individual things that would each
have to be true for that.

Each check is a dict with a "type" key selecting the dispatch, plus
whatever args that check needs:
    {"type": "file_exists", "path": ...}
    {"type": "file_not_empty", "path": ...}
    {"type": "file_modified_after", "path": ..., "timestamp": ...}
    {"type": "file_contains", "path": ..., "substring": ...}
    {"type": "file_hash_matches", "path": ..., "expected_hash": ...}
    {"type": "screenshot_changed", "before": ..., "after": ..., "min_difference": 0.02}
    {"type": "screenshot_matches_baseline", "label": ..., "path": ..., "similarity_threshold": 0.95}
    {"type": "result", "actual": ..., "expected": ..., "mode": "exact"|"contains"|"regex"|"numeric_range"|"type"}

Unrecognized "type" values fail closed (counted as a failed check,
never silently skipped) so a typo in a check never inflates the
score.
"""

import threading
from typing import Dict, List, Optional

from intelligence.verification.file_verifier import get_file_verifier
from intelligence.verification.screenshot_verifier import get_screenshot_verifier
from intelligence.verification.result_verifier import get_result_verifier

_instance: Optional["SuccessEvaluator"] = None
_instance_lock = threading.Lock()


class SuccessEvaluator:
    """Dispatches a mixed list of checks to the right verifier and
    aggregates them into one score/pass-fail."""

    def __init__(self):
        self._files = get_file_verifier()
        self._screenshots = get_screenshot_verifier()
        self._results = get_result_verifier()

    def _run_check(self, check: Dict) -> Dict:
        ctype = check.get("type")
        try:
            if ctype == "file_exists":
                return self._files.verify_exists(check["path"])
            if ctype == "file_not_empty":
                return self._files.verify_not_empty(check["path"])
            if ctype == "file_modified_after":
                return self._files.verify_modified_after(check["path"], check["timestamp"])
            if ctype == "file_contains":
                return self._files.verify_contains(check["path"], check["substring"])
            if ctype == "file_hash_matches":
                return self._files.verify_hash_matches(check["path"], check["expected_hash"])
            if ctype == "screenshot_changed":
                return self._screenshots.verify_changed(
                    check["before"], check["after"], check.get("min_difference", 0.02)
                )
            if ctype == "screenshot_matches_baseline":
                return self._screenshots.verify_against_baseline(
                    check["label"], check["path"], check.get("similarity_threshold", 0.95)
                )
            if ctype == "result":
                return self._results.verify(
                    check.get("actual"),
                    check.get("expected"),
                    check.get("mode", "exact"),
                    min_value=check.get("min_value"),
                    max_value=check.get("max_value"),
                )
        except KeyError as exc:
            return {"check": ctype, "passed": False, "reason": f"missing required field {exc}"}
        return {"check": ctype, "passed": False, "reason": f"unknown check type '{ctype}'"}

    def evaluate(self, checks: List[Dict], require_all: bool = True, pass_threshold: float = 1.0) -> Dict:
        """Run every check, then decide overall pass/fail: require_all=True
        means every check must pass; otherwise passes if score >=
        pass_threshold (fraction of checks that passed)."""
        if not checks:
            return {"passed": None, "score": 0.0, "results": [], "reason": "no checks provided"}

        results = [self._run_check(c) for c in checks]
        passed_count = sum(1 for r in results if r.get("passed"))
        score = round(passed_count / len(results), 4)

        overall_passed = (passed_count == len(results)) if require_all else (score >= pass_threshold)

        return {
            "passed": overall_passed,
            "score": score,
            "total_checks": len(results),
            "passed_checks": passed_count,
            "results": results,
        }


def get_success_evaluator() -> SuccessEvaluator:
    """Process-wide SuccessEvaluator singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SuccessEvaluator()
    return _instance
