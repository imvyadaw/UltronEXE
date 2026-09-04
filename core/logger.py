"""Central structured-ish logging for ULTRON.

All application loggers use :func:`get_logger`.  The logger deliberately
redacts credential-shaped values before they reach disk so a failed API call,
tool argument, or exception cannot accidentally turn a secret into a log
artifact.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)(\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(authorization|bearer)(\s*[=:]\s*)(?:bearer\s+)?([^\s,;]+)"),
    re.compile(
        r"(?i)\b(sk-[A-Za-z0-9_-]{12,}|gsk_[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9_-]{12,}|nvapi-[A-Za-z0-9_-]{12,})\b"
    ),
)


def _redact(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}<REDACTED>", text)
        else:
            text = pattern.sub("<REDACTED>", text)
    return text


class SecretRedactionFilter(logging.Filter):
    """Redact common credential formats from log messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(v) for k, v in record.args.items()}
            else:
                record.args = tuple(_redact(v) for v in record.args)
        return True


def get_logger(name: str = "ultron") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    from config import LOGS_DIR

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = RotatingFileHandler(LOGS_DIR / "ultron.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.addFilter(SecretRedactionFilter())
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger
