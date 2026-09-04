"""
Verification (Phase 19.4)
=============================
Confirms that actions/tasks actually had the effect they were
supposed to, instead of just assuming success once something ran
without an exception. Built to sit downstream of anything that
executes actions (e.g. Phase 18.7 automation, Phase 19.3's
goal_manager steps) - backed by a shared database at
database/verification.db:

    file_verifier.py       - filesystem checks: exists, modified/
                              created after a time, contains text,
                              hash/size matches
    screenshot_verifier.py - image-vs-image and image-vs-saved-
                              baseline comparison (pixel diff via
                              Pillow if installed, hash-equality
                              fallback otherwise)
    result_verifier.py     - actual-vs-expected checks on plain
                              values: exact, contains, regex,
                              numeric range, type
    action_verifier.py     - runs whichever file/screenshot checks
                              apply to one executed action, reports
                              pass/fail
    success_evaluator.py   - dispatches a mixed list of checks
                              (file/screenshot/result) to the right
                              verifier and rolls them into one score
    verification_engine.py - single entry point: runs a verification,
                              persists the outcome, and can be
                              queried for history afterwards

Usage:
    from intelligence.verification import get_verification_engine
    ve = get_verification_engine()
    ve.verify("export_report", checks=[
        {"type": "file_exists", "path": "/reports/q3.pdf"},
        {"type": "file_not_empty", "path": "/reports/q3.pdf"},
    ])
    ve.verify_action("click_export_button", checks={
        "expect_screenshot_changed": ["/tmp/before.png", "/tmp/after.png"],
    })
    ve.get_history(label="export_report")

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through the top-level engine.

Purely additive - nothing in Phase 1-19.3 imports from here.
"""

from intelligence.verification.file_verifier import FileVerifier, get_file_verifier
from intelligence.verification.screenshot_verifier import ScreenshotVerifier, get_screenshot_verifier
from intelligence.verification.result_verifier import ResultVerifier, get_result_verifier
from intelligence.verification.action_verifier import ActionVerifier, get_action_verifier
from intelligence.verification.success_evaluator import SuccessEvaluator, get_success_evaluator
from intelligence.verification.verification_engine import VerificationEngine, get_verification_engine

__all__ = [
    "VerificationEngine",
    "get_verification_engine",
    "FileVerifier",
    "get_file_verifier",
    "ScreenshotVerifier",
    "get_screenshot_verifier",
    "ResultVerifier",
    "get_result_verifier",
    "ActionVerifier",
    "get_action_verifier",
    "SuccessEvaluator",
    "get_success_evaluator",
]
