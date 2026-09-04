"""
Response Manager (Phase 21 - Unified Core Architecture)
========================================================
Scope note: conversation/response_builder.py already handles final
assembly for *proactive* alerts (tone_manager + context_engine, see its
own docstring). This module is the generic counterpart for everything
else that needs to leave the process - a normal reply to something the
user asked, an action_pipeline result, an autonomous_engine status
update - routed to whichever channel(s) it needs to reach (text reply,
voice via ui/voice_ui, a UI notification) without each caller
duplicating "turn this dict into text and figure out where it goes".

Channels are pluggable: register_formatter(channel, fn) overrides the
default formatter for that channel; register_deliverer(channel, fn)
overrides how it's actually sent (default is a no-op that just returns
the formatted text, so this module works with zero optional UI
packages installed - same "stdlib + graceful degradation" pattern as
the rest of core/). Every response is recorded on unified_context and
announced on event_bus as "response.ready" regardless of channel, so a
debug console can see everything that went out in one place.
"""

from typing import Any, Callable, Dict, Optional

from core.logger import get_logger

logger = get_logger("ultron.response_manager")


def _default_text_formatter(payload: Dict) -> str:
    if "text" in payload:
        return str(payload["text"])
    if payload.get("error"):
        return f"Something went wrong: {payload['error']}"
    if "result" in payload:
        return str(payload["result"])
    return str(payload)


class ResponseManager:
    def __init__(self):
        self._formatters: Dict[str, Callable[[Dict], str]] = {"text": _default_text_formatter}
        self._deliverers: Dict[str, Callable[[str, Dict], Any]] = {}

    def register_formatter(self, channel: str, fn: Callable[[Dict], str]) -> None:
        self._formatters[channel] = fn

    def register_deliverer(self, channel: str, fn: Callable[[str, Dict], Any]) -> None:
        self._deliverers[channel] = fn

    def respond(self, payload: Dict[str, Any], channel: str = "text", meta: Optional[Dict] = None) -> Dict[str, Any]:
        """Format `payload` for `channel`, deliver it if a deliverer is
        registered, record it on unified_context, and announce it on the
        event bus. Returns {"channel", "text", "delivered"}."""
        formatter = self._formatters.get(channel, _default_text_formatter)
        try:
            text = formatter(payload)
        except Exception:
            logger.exception(f"response_manager: formatter for channel '{channel}' failed")
            text = _default_text_formatter(payload)

        delivered = False
        deliverer = self._deliverers.get(channel)
        if deliverer:
            try:
                deliverer(text, payload)
                delivered = True
            except Exception:
                logger.exception(f"response_manager: deliverer for channel '{channel}' failed")

        try:
            from core.unified_context import get_unified_context

            get_unified_context().record_response(channel, text, meta=meta)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.response_manager.respond")

        try:
            from core.event_bus import get_event_bus

            get_event_bus().emit("response.ready", channel=channel, text=text, delivered=delivered)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("core.response_manager.respond")

        return {"channel": channel, "text": text, "delivered": delivered}

    def respond_to_action(self, action_result: Dict[str, Any], channel: str = "text") -> Dict[str, Any]:
        """Convenience wrapper for an core.action_pipeline result dict."""
        return self.respond(action_result, channel=channel, meta={"action": action_result.get("action")})


_manager: Optional[ResponseManager] = None


def get_response_manager() -> ResponseManager:
    global _manager
    if _manager is None:
        _manager = ResponseManager()
    return _manager
