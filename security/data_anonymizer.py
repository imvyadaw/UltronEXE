"""
Data anonymizer (Phase 26 - Security & Privacy)
==================================================
Pure-Python PII detection/redaction - no external dependencies, no I/O,
never raises on ordinary text. This is the lowest layer of the Phase 26
trio: security/privacy_guard.py decides *whether* something should be
anonymized before it leaves the machine (e.g. to a cloud LLM), and
security/encryption_manager.py decides *whether* something should be
encrypted before it touches disk - both call into this module to
actually find and mask the sensitive substrings; neither reimplements
pattern matching itself.

Detection is deliberately conservative (fewer false positives over
catching every possible PII shape) - a phone-number-shaped false
positive redacting a random 10-digit number is an annoying inconvenience;
a credit-card regex that's too loose and never fires is a silent
privacy hole. Credit cards are additionally Luhn-checked so a random
16-digit string (an order ID, a serial number) doesn't get flagged.

anonymize() is reversible within a single call: it returns a mapping of
generated tokens back to the original values, so a caller (privacy_guard,
talking to a cloud LLM) can send the redacted text out, get a reply back,
and restore the real values into the reply via deanonymize() - the
cloud model itself never sees the raw PII, but the user still does.
"""

import re
from typing import Dict, List, Optional

PII_CATEGORIES = ("email", "credit_card", "api_key", "ip_address", "phone")

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
# Grouped-or-plain 13-19 digit runs (with optional spaces/dashes between
# groups) - candidates only, Luhn-checked before being counted as a hit.
# Starts and ends on a digit so a trailing separator never gets pulled
# into the match.
_CARD_RE = re.compile(r"\b\d(?:[ -]?\d){11,17}\d\b")
# Known API-key prefixes (OpenAI, Google, GitHub, Slack, AWS, Anthropic)
# plus a generic fallback: a long (32+) run of hex/base64-ish characters
# with both letters and digits, which plain prose essentially never
# produces by accident.
_API_KEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9]{16,}|AIza[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[A-Z0-9]{12,}|"
    r"(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,})\b"
)
# Phone: an optional country code + 9-13 more digits, allowing spaces/
# dashes/dots/parens between groups - checked against a stripped digit
# count so "10-30-2026" style dates don't collide.
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}(?!\d)")


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


class DataAnonymizer:
    """scan() to detect, anonymize()/deanonymize() to redact-and-restore."""

    def scan(self, text: str) -> Dict[str, List[str]]:
        """Read-only detection - returns {category: [unique matches]} for
        every category with at least one hit. Never modifies `text`."""
        if not text:
            return {}
        found: Dict[str, List[str]] = {}

        emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))
        if emails:
            found["email"] = emails

        ips = list(dict.fromkeys(_IP_RE.findall(text)))
        if ips:
            found["ip_address"] = ips

        keys = list(dict.fromkeys(m.group(0) for m in _API_KEY_RE.finditer(text)))
        if keys:
            found["api_key"] = keys

        cards = []
        card_digit_spans = []
        for m in _CARD_RE.finditer(text):
            digits = _digits_only(m.group(0))
            if 13 <= len(digits) <= 19 and _luhn_valid(digits):
                cards.append(m.group(0))
                card_digit_spans.append(digits)
        if cards:
            found["credit_card"] = list(dict.fromkeys(cards))

        phones = []
        for m in _PHONE_RE.finditer(text):
            digits = _digits_only(m.group(0))
            # Skip anything that's really (part of) an already-matched
            # credit card, so the looser phone pattern doesn't also flag
            # a substring of a card number as a phone number.
            if 9 <= len(digits) <= 13 and not any(digits in card for card in card_digit_spans):
                phones.append(m.group(0))
        if phones:
            found["phone"] = list(dict.fromkeys(phones))

        return found

    def anonymize(self, text: str) -> Dict:
        """Replaces every detected PII substring with a `[REDACTED_<CATEGORY>_n]`
        token. Returns {"success", "text", "mapping" (token -> original),
        "found" (category -> count)}. The same original value always maps
        to the same token within one call, so a repeated email address
        doesn't burn multiple token slots."""
        if not text:
            return {"success": True, "text": text, "mapping": {}, "found": {}}

        found = self.scan(text)
        mapping: Dict[str, str] = {}
        counts: Dict[str, int] = {}
        value_to_token: Dict[str, str] = {}
        result = text

        # Longest/most-specific categories first so e.g. a credit card
        # number isn't partially eaten by the looser phone pattern first.
        for category in ("credit_card", "api_key", "email", "ip_address", "phone"):
            for original in found.get(category, []):
                if original in value_to_token:
                    token = value_to_token[original]
                else:
                    counts[category] = counts.get(category, 0) + 1
                    token = f"[REDACTED_{category.upper()}_{counts[category]}]"
                    value_to_token[original] = token
                    mapping[token] = original
                result = result.replace(original, token)

        return {
            "success": True,
            "text": result,
            "mapping": mapping,
            "found": {c: len(v) for c, v in found.items()},
        }

    def deanonymize(self, text: str, mapping: Dict[str, str]) -> str:
        """Restores tokens produced by anonymize() back to their original
        values. Safe no-op for tokens not present in `text` or `mapping`
        missing/empty - never raises."""
        if not text or not mapping:
            return text
        restored = text
        for token, original in mapping.items():
            restored = restored.replace(token, original)
        return restored

    def has_pii(self, text: str, categories: Optional[List[str]] = None) -> bool:
        """Convenience boolean - True if `text` contains any PII (optionally
        restricted to `categories`)."""
        found = self.scan(text)
        if categories:
            return any(c in found for c in categories)
        return bool(found)


_anonymizer: Optional[DataAnonymizer] = None


def get_data_anonymizer() -> DataAnonymizer:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = DataAnonymizer()
    return _anonymizer
