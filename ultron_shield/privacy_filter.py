"""
privacy_filter.py
====================
Scrubs sensitive-looking substrings - API keys, credit-card-shaped
numbers, emails, phone numbers, anything matching a pattern you add -
out of text before it hits a log file, gets displayed back, or is
sent anywhere. Meant to sit in front of logging calls and outbound
messages across the rest of ULTRON (e.g. wrap `logger.info(...)`
calls, or run over what `notification_router` is about to send).

Rules are regex + a fixed replacement token, evaluated in the order
added; built-ins cover the common shapes (email, phone, credit card,
generic API-key-looking tokens) and you can add your own via
`add_rule()`. This is pattern matching, not semantic understanding -
it will miss sensitive data that doesn't match a known shape, and
occasionally redact things that only look like one; treat it as a
safety net under existing good practices (like `secure_enclave.py`
never logging values), not a substitute for them.

Pure standard library.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Pattern

logger = logging.getLogger("ultron.privacy_filter")


@dataclass
class RedactionRule:
    name: str
    pattern: Pattern
    replacement: str


def _default_rules() -> List[RedactionRule]:
    return [
        RedactionRule("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
        RedactionRule("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[REDACTED_CARD_NUMBER]"),
        RedactionRule(
            "phone_number",
            re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "[REDACTED_PHONE]",
        ),
        RedactionRule(
            "api_key_like",
            re.compile(r"\b(?:sk|pk|api|key|token)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE),
            "[REDACTED_KEY]",
        ),
        RedactionRule("ssn_like", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
        RedactionRule("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
    ]


class PrivacyFilter:
    """Applies an ordered list of redaction rules to text."""

    def __init__(self, include_defaults: bool = True):
        self._rules: List[RedactionRule] = _default_rules() if include_defaults else []

    def add_rule(self, name: str, pattern: str, replacement: str, flags: int = 0) -> None:
        self._rules.append(RedactionRule(name, re.compile(pattern, flags), replacement))
        logger.info("Added privacy rule '%s'", name)

    def remove_rule(self, name: str) -> bool:
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) != before

    def redact(self, text: str) -> str:
        for rule in self._rules:
            text = rule.pattern.sub(rule.replacement, text)
        return text

    def scan(self, text: str) -> List[str]:
        """Return names of rules that matched, without modifying the text -
        useful for a 'this looks like it might contain a secret, are you
        sure?' confirmation prompt before sending something."""
        return [rule.name for rule in self._rules if rule.pattern.search(text)]

    def make_logging_filter(self) -> logging.Filter:
        """Returns a `logging.Filter` you can attach to any logger/handler so
        every record's message is redacted automatically:

            handler.addFilter(privacy_filter.make_logging_filter())
        """
        outer = self

        class _RedactingFilter(logging.Filter):
            def filter(self, record: logging.LogRecord) -> bool:
                if isinstance(record.msg, str):
                    record.msg = outer.redact(record.msg)
                return True

        return _RedactingFilter()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pf = PrivacyFilter()

    text = (
        "Contact me at jane.doe@example.com or 555-123-4567. "
        "My key is sk-ABCDEF1234567890abcdef and card 4111 1111 1111 1111."
    )
    print("Original scan hits:", pf.scan(text))
    print("Redacted:", pf.redact(text))

    pf.add_rule("employee_id", r"\bEMP-\d{6}\b", "[REDACTED_EMP_ID]")
    print("Custom rule:", pf.redact("Badge EMP-123456 checked in."))
