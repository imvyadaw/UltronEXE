"""
Result Verifier (Phase 19.4 - Verification)
===============================================
Stateless comparisons of an actual value (command output, API
response, computed result, ...) against what was expected: exact
match, substring, regex, numeric range, or type check. Every method
returns a {"passed": bool, ...details} dict, same shape as
file_verifier.py, so success_evaluator.py can treat every verifier
uniformly.
"""

import re
import threading
from typing import Any, Dict, Optional, Type

_instance: Optional["ResultVerifier"] = None
_instance_lock = threading.Lock()


class ResultVerifier:
    """Actual-vs-expected comparisons for non-filesystem, non-visual
    results."""

    def verify_exact(self, actual: Any, expected: Any) -> Dict:
        return {"check": "exact", "passed": actual == expected, "actual": actual, "expected": expected}

    def verify_contains(self, actual: str, expected_substring: str) -> Dict:
        passed = isinstance(actual, str) and expected_substring in actual
        return {"check": "contains", "passed": passed, "actual": actual, "expected_substring": expected_substring}

    def verify_regex(self, actual: str, pattern: str) -> Dict:
        if not isinstance(actual, str):
            return {
                "check": "regex",
                "passed": False,
                "actual": actual,
                "pattern": pattern,
                "reason": "actual is not a string",
            }
        match = re.search(pattern, actual)
        return {
            "check": "regex",
            "passed": match is not None,
            "actual": actual,
            "pattern": pattern,
            "matched_text": match.group(0) if match else None,
        }

    def verify_numeric_range(
        self, actual: Any, min_value: Optional[float] = None, max_value: Optional[float] = None
    ) -> Dict:
        try:
            value = float(actual)
        except (TypeError, ValueError):
            return {"check": "numeric_range", "passed": False, "actual": actual, "reason": "actual is not numeric"}
        passed = (min_value is None or value >= min_value) and (max_value is None or value <= max_value)
        return {
            "check": "numeric_range",
            "passed": passed,
            "actual": value,
            "min_value": min_value,
            "max_value": max_value,
        }

    def verify_type(self, actual: Any, expected_type: Type) -> Dict:
        return {
            "check": "type",
            "passed": isinstance(actual, expected_type),
            "actual_type": type(actual).__name__,
            "expected_type": expected_type.__name__,
        }

    def verify(self, actual: Any, expected: Any = None, mode: str = "exact", **kwargs) -> Dict:
        """Single dispatcher so callers/success_evaluator can pick a mode
        by string instead of calling a specific method:
        mode in {"exact", "contains", "regex", "numeric_range", "type"}."""
        if mode == "exact":
            return self.verify_exact(actual, expected)
        if mode == "contains":
            return self.verify_contains(actual, expected)
        if mode == "regex":
            return self.verify_regex(actual, expected)
        if mode == "numeric_range":
            return self.verify_numeric_range(actual, kwargs.get("min_value"), kwargs.get("max_value"))
        if mode == "type":
            return self.verify_type(actual, expected)
        return {"check": mode, "passed": False, "reason": f"unknown mode '{mode}'"}


def get_result_verifier() -> ResultVerifier:
    """Process-wide ResultVerifier singleton (stateless, but shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ResultVerifier()
    return _instance
