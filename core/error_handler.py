"""
Error Handler
=============
Centralized error classification + recovery for tool execution. Every
other new core/ module (task_queue, workflow_engine) that runs tool
calls asynchronously or in a loop routes through here instead of
letting a raw exception/error dict bubble up and kill the run - one
place decides what's retryable, what's fatal, and logs consistently.

Usage:
    from core.error_handler import get_error_handler
    eh = get_error_handler()
    result = eh.run_safely(execute_tool, "open_application", {"app_name": "chrome"})
    # -> {"success": True, "result": {...}} or
    #    {"success": False, "error": "...", "category": "...", "attempts": N}
"""

import json
import time
import traceback
from typing import Callable, Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.error_handler")

_handler: Optional["ErrorHandler"] = None

# Error categories drive retry behaviour: transient stuff (network,
# temporary file locks) is worth retrying; a bad argument or unknown
# tool never magically works on retry #2.
RETRYABLE_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "network",
    "econnreset",
    "resource busy",
    "access is denied while",
)
NON_RETRYABLE_MARKERS = (
    "unknown tool",
    "not found",
    "invalid",
    "permission denied",
    "does not exist",
    "not supported",
)


class ExecutionError(Exception):
    """Raised internally to unify 'exception' and '{"error": ...}' result
    shapes into one thing run_safely() can classify and log."""

    def __init__(self, message: str, category: str = "unknown"):
        super().__init__(message)
        self.category = category


class ErrorHandler:
    """Wrap any tool/step callable with classification, retry, and logging."""

    def classify(self, message: str) -> str:
        lower = (message or "").lower()
        if any(m in lower for m in RETRYABLE_MARKERS):
            return "transient"
        if any(m in lower for m in NON_RETRYABLE_MARKERS):
            return "permanent"
        return "unknown"

    def run_safely(
        self,
        func: Callable,
        *args,
        max_retries: int = 1,
        retry_backoff: float = 1.0,
        context: str = "",
        **kwargs,
    ) -> Dict:
        """Call `func(*args, **kwargs)`, retrying transient failures.

        Understands both raw exceptions and Ultron's usual convention of
        returning a JSON string / dict containing an "error" key (see
        core/executor.py). Always returns a plain dict, never raises.
        """
        attempts = 0
        last_error = None
        last_category = "unknown"

        while attempts <= max_retries:
            attempts += 1
            try:
                raw = func(*args, **kwargs)
                parsed = raw
                if isinstance(raw, str):
                    try:
                        parsed = json.loads(raw)
                    except (ValueError, TypeError):
                        parsed = raw

                if isinstance(parsed, dict) and parsed.get("error"):
                    last_error = str(parsed["error"])
                    last_category = self.classify(last_error)
                    if last_category != "transient" or attempts > max_retries:
                        logger.warning(
                            f"[{context or getattr(func, '__name__', 'call')}] failed "
                            f"(attempt {attempts}/{max_retries + 1}, category={last_category}): {last_error}"
                        )
                        return {
                            "success": False,
                            "error": last_error,
                            "category": last_category,
                            "attempts": attempts,
                        }
                    time.sleep(retry_backoff * attempts)
                    continue

                return {"success": True, "result": parsed, "attempts": attempts}

            except Exception as e:
                last_error = str(e)
                last_category = self.classify(last_error)
                logger.error(
                    f"[{context or getattr(func, '__name__', 'call')}] exception "
                    f"(attempt {attempts}/{max_retries + 1}): {e}\n{traceback.format_exc()}"
                )
                if last_category != "transient" or attempts > max_retries:
                    return {
                        "success": False,
                        "error": last_error,
                        "category": last_category,
                        "attempts": attempts,
                    }
                time.sleep(retry_backoff * attempts)

        return {
            "success": False,
            "error": last_error or "Unknown failure",
            "category": last_category,
            "attempts": attempts,
        }


def get_error_handler() -> ErrorHandler:
    global _handler
    if _handler is None:
        _handler = ErrorHandler()
    return _handler
