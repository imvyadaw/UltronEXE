"""
ui.bridge - the one place every UI surface (web_ui, mobile/api, voice_ui)
goes through to talk to Ultron core.

Why this exists: web_ui/app.py, mobile/api/routes.py, and voice_ui's
avatar controller all need the same three things - send a message and
get a reply, check auth/session state, and read health/monitoring
status. Rather than each surface importing core.* directly (and each
breaking separately if a core module isn't present yet), they all
import from here.

Mirrors the Phase 6 pattern noted in
docs/architecture/phase6_config_storage.md: config/*.yaml documents
target values that nothing reads yet. Same idea here - this module
documents the target integration surface. If the real core modules
are importable, it uses them. If not (e.g. running this UI scaffold
standalone, or core hasn't caught up yet), it does not silently fall back to a fake assistant in production. A stub is
available only when the explicit ULTRON_UI_ALLOW_STUB=1 environment variable
is set for development/testing.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("ultron.ui.bridge")

# ---------------------------------------------------------------------------
# Attempt real core integration first. Every one of these is expected NOT
# to exist yet in a fresh Phase 6 checkout - that's fine, we fall back.
# ---------------------------------------------------------------------------
_core_assistant = None
_core_auth = None
_core_health = None

try:
    from core.assistant import get_assistant as _get_assistant  # type: ignore

    # Assistant.__init__ requires (client, processor) - get_assistant() is
    # the existing factory that builds the default Groq-backed brain and
    # slash-command processor when neither is supplied. Calling Assistant()
    # directly (the old code here) always raised TypeError and silently
    # fell back to the stub below - this is why /api/v1/chat and
    # /api/v1/status showed source":"stub" / "assistant": false even
    # though core.assistant.Assistant existed and imported fine.
    _core_assistant = _get_assistant()
except Exception:  # pragma: no cover - expected until core wires this up
    logger.exception("core.assistant.get_assistant() failed - UI core unavailable")
    _core_assistant = None

try:
    from security.authentication import AuthManager as _AuthManager  # type: ignore

    _core_auth = _AuthManager()
except Exception:  # pragma: no cover
    _core_auth = None

try:
    from monitoring.health_check import get_health_status as _get_health_status  # type: ignore

    _core_health = _get_health_status
except Exception:  # pragma: no cover
    _core_health = None


@dataclass
class ChatReply:
    session_id: str
    reply: str
    source: str  # "core" | "stub" | "unavailable"
    timestamp: float = field(default_factory=time.time)


class _StubAssistant:
    """
    Minimal in-memory stand-in so every UI surface works before core
    is wired in. Keeps per-session history only for the life of the
    process - nothing here touches storage/.
    """

    def __init__(self) -> None:
        self._history: dict[str, list[dict]] = {}

    def handle_message(self, text: str, session_id: str | None = None) -> ChatReply:
        session_id = session_id or str(uuid.uuid4())
        history = self._history.setdefault(session_id, [])
        history.append({"role": "user", "text": text, "ts": time.time()})

        reply_text = "(stub) Ultron core isn't wired into the UI layer yet - " f"echoing what I received: {text!r}"
        history.append({"role": "assistant", "text": reply_text, "ts": time.time()})
        return ChatReply(session_id=session_id, reply=reply_text, source="stub")

    def get_history(self, session_id: str) -> list[dict]:
        return self._history.get(session_id, [])


_stub = _StubAssistant()
_ALLOW_STUB = os.getenv("ULTRON_UI_ALLOW_STUB", "0").strip().lower() in {"1", "true", "yes", "on"}


def _unavailable_reply(session_id: str | None, detail: str) -> ChatReply:
    """Return an explicit unavailable state; never masquerade as Ultron."""
    sid = session_id or str(uuid.uuid4())
    return ChatReply(
        session_id=sid,
        reply=("Ultron core is unavailable. The UI did not execute the request. " f"Reason: {detail}"),
        source="unavailable",
    )


def send_message(text: str, session_id: str | None = None) -> ChatReply:
    """Single entry point every UI surface calls to talk to Ultron.

    Production is fail-closed: if the real core is unavailable or raises, the
    UI returns an explicit error instead of an echo that could be mistaken for
    a successful assistant response. Set ULTRON_UI_ALLOW_STUB=1 only for local
    UI development/testing.
    """
    if _core_assistant is not None:
        try:
            result = _core_assistant.handle_message(text, session_id=session_id)
            return ChatReply(
                session_id=session_id or str(uuid.uuid4()),
                reply=str(result),
                source="core",
            )
        except Exception as exc:
            logger.exception("core.assistant.handle_message failed")
            from ui.notifications import report_error

            report_error(f"Ultron core failed to answer: {exc}", source="bridge.send_message")
            if not _ALLOW_STUB:
                return _unavailable_reply(session_id, f"{type(exc).__name__}: {exc}")
    elif not _ALLOW_STUB:
        return _unavailable_reply(session_id, "core.assistant could not be initialized")
    return _stub.handle_message(text, session_id=session_id)


def get_history(session_id: str) -> list[dict]:
    if _core_assistant is not None and hasattr(_core_assistant, "get_history"):
        try:
            return _core_assistant.get_history(session_id)
        except Exception:
            logger.exception("core.assistant.get_history failed")
            if not _ALLOW_STUB:
                return []
    if _ALLOW_STUB:
        return _stub.get_history(session_id)
    return []


def get_health() -> dict:
    if _core_health is not None:
        try:
            return _core_health()
        except Exception:
            logger.exception("monitoring.health_check.get_health_status failed")
    if _ALLOW_STUB:
        return {"status": "unknown", "detail": "monitoring module not wired in yet", "source": "stub"}
    return {"status": "unavailable", "detail": "monitoring module is not connected", "source": "unavailable"}


def core_wired() -> dict:
    """Diagnostic - what's actually connected right now. Used by /api/v1/status."""
    return {
        "assistant": _core_assistant is not None,
        "auth": _core_auth is not None,
        "health_check": _core_health is not None,
    }
