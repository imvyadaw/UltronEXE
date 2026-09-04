"""
utils/validators.py - cheap, dependency-free input validation. These
are sanity checks (is this shaped like an email?), not full RFC-grade
parsing - skills/email and networking/ should still handle their own
protocol-level validation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Union

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s]+$")


def is_valid_email(value: Any) -> bool:
    """
    >>> is_valid_email("a@b.com")
    True
    >>> is_valid_email("not-an-email")
    False
    """
    return isinstance(value, str) and bool(_EMAIL_RE.match(value.strip()))


def is_valid_url(value: Any) -> bool:
    """
    >>> is_valid_url("https://example.com/path")
    True
    >>> is_valid_url("example.com")
    False
    """
    return isinstance(value, str) and bool(_URL_RE.match(value.strip()))


def is_valid_path(value: Union[str, Path], must_exist: bool = False) -> bool:
    """
    >>> is_valid_path(".", must_exist=True)
    True
    """
    try:
        path = Path(value)
    except TypeError:
        return False
    if must_exist:
        return path.exists()
    return True


def is_non_empty_str(value: Any) -> bool:
    """
    >>> is_non_empty_str("  hi  ")
    True
    >>> is_non_empty_str("   ")
    False
    """
    return isinstance(value, str) and bool(value.strip())
