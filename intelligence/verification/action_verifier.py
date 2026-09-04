"""
Action Verifier (Phase 19.4 - Verification)
===============================================
Verifies that an already-executed action actually had the effect it
was supposed to, by running whichever file_verifier.py /
screenshot_verifier.py checks apply to that action. This module owns
no storage and makes no decisions about *what* to check - a caller
(typically success_evaluator.py, or whatever in ULTRON just ran the
action) passes in a checks dict describing what "worked" would look
like, and gets back each individual check plus an overall passed
flag.

Recognized check keys (all optional, any combination):
    expect_file                    -> path that should now exist
    expect_file_not_empty          -> path that should exist and be non-empty
    expect_file_modified_after     -> (path, timestamp) tuple/list
    expect_file_contains           -> (path, substring) tuple/list
    expect_screenshot_changed      -> (before_path, after_path) tuple/list
    expect_screenshot_matches_baseline -> (label, current_path) tuple/list
"""

import threading
from typing import Dict, List, Optional

from intelligence.verification.file_verifier import get_file_verifier
from intelligence.verification.screenshot_verifier import get_screenshot_verifier

_instance: Optional["ActionVerifier"] = None
_instance_lock = threading.Lock()


class ActionVerifier:
    """Runs the file/screenshot checks relevant to one executed action
    and reports whether all of them passed."""

    def __init__(self):
        self._files = get_file_verifier()
        self._screenshots = get_screenshot_verifier()

    def verify_action(self, action_name: str, checks: Optional[Dict] = None) -> Dict:
        checks = checks or {}
        results: List[Dict] = []

        if "expect_file" in checks:
            results.append(self._files.verify_exists(checks["expect_file"]))

        if "expect_file_not_empty" in checks:
            results.append(self._files.verify_not_empty(checks["expect_file_not_empty"]))

        if "expect_file_modified_after" in checks:
            path, timestamp = checks["expect_file_modified_after"]
            results.append(self._files.verify_modified_after(path, timestamp))

        if "expect_file_contains" in checks:
            path, substring = checks["expect_file_contains"]
            results.append(self._files.verify_contains(path, substring))

        if "expect_screenshot_changed" in checks:
            before, after = checks["expect_screenshot_changed"]
            results.append(self._screenshots.verify_changed(before, after))

        if "expect_screenshot_matches_baseline" in checks:
            label, current = checks["expect_screenshot_matches_baseline"]
            results.append(self._screenshots.verify_against_baseline(label, current))

        if not results:
            return {"action": action_name, "passed": None, "checks": [], "reason": "no checks provided"}

        passed = all(r.get("passed") for r in results)
        return {"action": action_name, "passed": passed, "checks": results}


def get_action_verifier() -> ActionVerifier:
    """Process-wide ActionVerifier singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ActionVerifier()
    return _instance
