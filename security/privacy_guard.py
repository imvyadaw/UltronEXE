"""
Privacy guard (Phase 26 - Security & Privacy)
================================================
Policy layer sitting in front of every outbound cloud AI call - wired
into ai/ai_router.py's _attempt_cloud() path (see the router's
_attempt_cloud_guarded()) so nothing the user types reaches Groq/NVIDIA/
DeepSeek/OpenRouter/Gemini without first being screened, exactly the
same way security/vault.py sits in front of security/encryption.py so
callers get consistent policy instead of each one deciding for itself.

Two tiers, using security/data_anonymizer.py's detection:
  BLOCK_CATEGORIES     - too sensitive to send even masked (credit card
                          numbers, API keys/tokens) - screen_for_cloud()
                          refuses the cloud attempt entirely for that
                          turn, ai_router falls back to local exactly as
                          if the cloud backend itself had failed.
  ANONYMIZE_CATEGORIES - fine to send once masked (email, phone, IP) -
                          the cloud model sees `[REDACTED_EMAIL_1]`
                          tokens instead of the real value, and
                          restore_response() puts the real values back
                          into the reply before the user sees it, so the
                          answer still reads naturally.

Every screening decision (never the raw matched PII itself) is logged
to security/audit.py, so "did anything sensitive almost go to the
cloud this week" is answerable the same way vault access already is.

Off by default is NOT an option that silently disables screening and
also silently sends things - set_enabled(False) still logs that
screening was skipped, so a user who disabled this can't later be
surprised by it having been off.
"""

from typing import Dict, List, Optional

from security.data_anonymizer import get_data_anonymizer
from core.logger import get_logger

logger = get_logger("ultron.security.privacy_guard")

BLOCK_CATEGORIES = {"credit_card", "api_key"}
ANONYMIZE_CATEGORIES = {"email", "phone", "ip_address"}


class PrivacyGuard:
    """screen_for_cloud() before sending, restore_response() after."""

    def __init__(self):
        self._anonymizer = get_data_anonymizer()
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._audit().record("privacy_guard_toggle", {"enabled": enabled}, success=True)
        logger.info(f"Privacy guard {'enabled' if enabled else 'disabled'}.")

    def is_enabled(self) -> bool:
        return self._enabled

    def screen_for_cloud(self, text: str) -> Dict:
        """Returns {"allowed", "text" (what's actually safe to send),
        "mapping" (token->original, for restore_response), "categories_found",
        "reason"}. `text` is unchanged and `allowed` is True when nothing
        sensitive is found - the common case, and also what's returned
        (with a logged note) when the guard itself is disabled."""
        if not self._enabled:
            self._audit().record("privacy_guard_skipped", {}, success=True)
            return {
                "allowed": True,
                "text": text,
                "mapping": {},
                "categories_found": [],
                "reason": "privacy guard disabled",
            }

        if not text:
            return {"allowed": True, "text": text, "mapping": {}, "categories_found": [], "reason": "empty message"}

        found = self._anonymizer.scan(text)
        categories_found = list(found.keys())

        blocked = [c for c in categories_found if c in BLOCK_CATEGORIES]
        if blocked:
            self._audit().record("privacy_guard_block", {"categories": blocked}, success=True)
            logger.info(f"Cloud send blocked - detected: {', '.join(blocked)}")
            return {
                "allowed": False,
                "text": None,
                "mapping": {},
                "categories_found": categories_found,
                "reason": f"detected {', '.join(blocked)} - kept local-only for this turn",
            }

        to_anonymize = [c for c in categories_found if c in ANONYMIZE_CATEGORIES]
        if to_anonymize:
            result = self._anonymizer.anonymize(text)
            self._audit().record("privacy_guard_anonymize", {"categories": to_anonymize}, success=True)
            logger.info(f"Anonymized before cloud send: {', '.join(to_anonymize)}")
            return {
                "allowed": True,
                "text": result["text"],
                "mapping": result["mapping"],
                "categories_found": categories_found,
                "reason": "anonymized before sending to cloud",
            }

        return {
            "allowed": True,
            "text": text,
            "mapping": {},
            "categories_found": [],
            "reason": "no sensitive data detected",
        }

    def restore_response(self, response_text: str, mapping: Dict[str, str]) -> str:
        """Puts real values back into a cloud reply that may echo one of
        the redaction tokens back (e.g. confirming an email address it
        was asked to use). No-op if there's nothing to restore."""
        if not response_text or not mapping:
            return response_text
        return self._anonymizer.deanonymize(response_text, mapping)

    def recent_decisions(self, limit: int = 20) -> List[Dict]:
        """Recent block/anonymize/skip decisions, for a settings/audit UI -
        thin passthrough to security/audit.py, filtered to this guard's
        own event types."""
        audit = self._audit()
        events: List[Dict] = []
        for event_type in ("privacy_guard_block", "privacy_guard_anonymize", "privacy_guard_skipped"):
            events.extend(audit.by_type(event_type, limit=limit).get("events", []))
        events.sort(key=lambda e: e.get("created_at", 0), reverse=True)
        return events[:limit]

    def _audit(self):
        from security.audit import get_audit_log

        return get_audit_log()


_guard: Optional[PrivacyGuard] = None


def get_privacy_guard() -> PrivacyGuard:
    global _guard
    if _guard is None:
        _guard = PrivacyGuard()
    return _guard
