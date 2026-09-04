"""
Guard Agent
===========
Written first among the six because coder.py, writer.py, researcher.py,
and analyst.py all describe piping their output through this module
before it reaches the user or core/executor.py - this is the module
those references point at.

Deliberately rule-based, not LLM-based, and deliberately not the same
job as PHASE_17_2_COGNITIVE_BRAIN/COGNITIVE_CORE/self_critique_agent.py:
that module judges whether a goal was *achieved*, this one judges
whether a piece of content is *safe to act on or show*. Two different
questions, two different mechanisms - a model judging its own safety
is the thing this module exists to not depend on. Same auditable,
no-black-box instinct as MEMORY/forget.py: every flag GuardAgent raises
traces back to one named pattern in DANGEROUS_CODE_PATTERNS or
SENSITIVE_TEXT_PATTERNS, not a model's unexplained opinion.

review() never raises and never blocks by itself - it only reports.
Callers (e.g. whatever hands coder.py's output to core/executor.py)
decide what to do with a non-empty `flags` list; this module's job
ends at telling them what it found.
"""

import re
from typing import Dict, List

DANGEROUS_CODE_PATTERNS = [
    (r"\bos\.system\s*\(", "shell command via os.system"),
    (r"\bsubprocess\.\w+\([^)]*shell\s*=\s*True", "subprocess call with shell=True"),
    (r"\beval\s*\(", "use of eval()"),
    (r"\bexec\s*\(", "use of exec()"),
    (r"rm\s+-rf\s+/", "recursive force-delete from root"),
    (r"\bshutil\.rmtree\s*\(", "recursive directory delete via shutil.rmtree"),
    (r"\b__import__\s*\(", "dynamic import via __import__()"),
    (r"\bpickle\.loads?\s*\(", "pickle deserialization (arbitrary code execution risk)"),
    (r"chmod\s+777", "world-writable permission change"),
    (r"(?i)\b(api[_-]?key|secret|password|token)\s*=\s*[\"'][^\"']{6,}[\"']", "hardcoded credential-looking literal"),
    (r"(?i)curl\s+.*\|\s*(sh|bash)", "pipe a remote download straight into a shell"),
]

SENSITIVE_TEXT_PATTERNS = [
    (r"[\w.+-]+@[\w-]+\.[\w.-]+", "email address"),
    (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone-number-shaped string"),
    (r"\b(?:\d[ -]*?){13,16}\b", "credit-card-shaped number"),
    (r"(?i)\b(ssn|social security number)\b", "explicit SSN reference"),
]


class GuardAgent:
    """Rule-based safety/policy review for other agents' output. Use get_guard()."""

    def is_available(self) -> bool:
        # Pure regex over stdlib - nothing external to be unavailable.
        return True

    def review_code(self, code: str) -> Dict:
        """Scans `code` against DANGEROUS_CODE_PATTERNS. Returns
        {"safe": bool, "flags": [{"pattern": str, "reason": str}]}.
        `safe` is just `not flags` - this method never decides what
        happens next, only what it found."""
        flags: List[Dict] = []
        if code:
            for pattern, reason in DANGEROUS_CODE_PATTERNS:
                if re.search(pattern, code):
                    flags.append({"pattern": pattern, "reason": reason})
        return {"safe": not flags, "flags": flags}

    def review_text(self, text: str) -> Dict:
        """Scans `text` against SENSITIVE_TEXT_PATTERNS. Same
        {"safe": bool, "flags": [...]} shape as review_code() - a hit
        here means "this text contains what looks like PII", not that
        the text is malicious; callers writer.py/teacher.py feed
        through this should decide redact-vs-block for themselves."""
        flags: List[Dict] = []
        if text:
            for pattern, reason in SENSITIVE_TEXT_PATTERNS:
                if re.search(pattern, text):
                    flags.append({"pattern": pattern, "reason": reason})
        return {"safe": not flags, "flags": flags}

    def review(self, content: str, kind: str = "code") -> Dict:
        """Dispatches to review_code() or review_text() by `kind`
        ("code" or "text"). Unknown `kind` collapses to
        {"safe": True, "flags": []} rather than raising - an agent
        that doesn't know how to classify its own output shouldn't be
        blocked by this module for that reason alone."""
        if kind == "code":
            return self.review_code(content)
        if kind == "text":
            return self.review_text(content)
        return {"safe": True, "flags": []}


_guard: "GuardAgent | None" = None


def get_guard() -> GuardAgent:
    global _guard
    if _guard is None:
        _guard = GuardAgent()
    return _guard
