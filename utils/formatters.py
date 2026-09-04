"""
utils/formatters.py - turn raw values into human-readable strings.
scripts/maintenance.py has its own local human_size() predating this
file; this is the shared version new code should import instead.
"""

from __future__ import annotations

import re

from utils.constants import ONE_KB


def human_size(num_bytes: float) -> str:
    """
    >>> human_size(500)
    '500.0B'
    >>> human_size(1536)
    '1.5KB'
    """
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < ONE_KB:
            return f"{size:.1f}{unit}"
        size /= ONE_KB
    return f"{size:.1f}TB"


def human_duration(seconds: float) -> str:
    """
    >>> human_duration(90)
    '1m 30s'
    >>> human_duration(45)
    '45s'
    """
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    >>> truncate("hello world", 5)
    'he...'
    """
    if len(text) <= max_length:
        return text
    if max_length <= len(suffix):
        return suffix[:max_length]
    return text[: max_length - len(suffix)] + suffix


def slugify(text: str) -> str:
    """
    >>> slugify("Hello, Ultron!  Phase 15")
    'hello-ultron-phase-15'
    """
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
