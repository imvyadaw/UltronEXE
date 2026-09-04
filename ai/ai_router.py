"""
AI Router
=========
The single entry point every part of Ultron goes through to talk to an
LLM. Nothing else should import ai/cloud_models/groq_client.py or
ai/local_models/manager.py directly and call them - core/brain.get_brain()
returns this router, and this router decides, per turn, whether Groq
(cloud) or Ollama (local) actually handles it.

Routing policy (config.AI_MODE == "auto", the default):
    online  -> try cloud backends in order: Groq -> NVIDIA -> DeepSeek ->
               OpenRouter -> xKiro -> Gemini
               all fail/error -> automatically fall back to local (Ollama)
    offline -> use local directly
               local unavailable  -> clear, honest error message; no crash
    internet returns mid-session -> next turn automatically tries cloud
               again (nothing to "switch back" explicitly - is_online() is
               re-checked every single turn).

Each cloud backend is optional - only ones with an API key configured in
.env are used at all. E.g. if GROQ_API_KEY is set but nothing else is, this
degrades gracefully to just Groq -> Ollama, same as before. Whichever
backend actually answers a turn is both logged (storage/logs/ultron.log)
and printed to the console as "[AI: <name>] ..." so you can see it live,
not just after the fact in the log file.

config.AI_MODE == "cloud" / "local" forces one backend for the whole
process (debugging/testing a single path in isolation) with no fallback.

Both backends share ONE conversation history (self.history). Cloud and
local clients each keep a `conversation_history` attribute that this
router points at the exact same list object, so whichever backend
answers a given turn, the next turn - on either backend - sees the full
conversation so far. That's what lets a session hop cloud -> local -> cloud
without the assistant "forgetting" what was just discussed.
"""

import time
from typing import Callable, Dict, List, Optional

from config import AI_MODE, MODEL_NAME, OLLAMA_MODEL, CLOUD_MAX_RETRIES, CLOUD_RETRY_BACKOFF_SECONDS
from core.internet_monitor import is_online
from core.logger import get_logger

logger = get_logger("ai_router")

# Cloud responses that mean "this didn't really work", even though
# UltronGroqClient.chat_with_tools() returned a string instead of raising -
# the router treats these the same as a raised exception: fall back to local.
#
# BUG FIXED: every cloud client (groq/nvidia/deepseek/xkiro/gemini/
# openrouter) has a SECOND failure path for when the tool-RESULT
# follow-up call fails (after a tool already ran successfully) - it
# returns f"Error while processing the result (...): {e}", not
# "Error: ...". That string didn't match any prefix here, so the router
# treated it as a genuine successful reply, printed "[AI: <name>]
# answered this turn", and handed the raw error text straight to the
# user instead of retrying or falling through to the next backend/local.
# Seen live: NVIDIA ran search_internet fine, then its follow-up call
# 500'd, and the 500 error text got spoken back as if it were the answer.
_CLOUD_FAILURE_PREFIXES = (
    "Error:",
    "Error while processing the result",
    "I have hit my rate limit on all safe channels",
)


def _looks_like_cloud_failure(response: str) -> bool:
    return any(response.startswith(p) for p in _CLOUD_FAILURE_PREFIXES)


class AIRouter:
    """Centralized router: internet detection, model selection, fallback,
    retry, shared context, and basic performance tracking."""

    # Cloud backends in fallback order. Each entry is (name, module path,
    # getter function name). Every getter raises if its API key is missing,
    # which _get_cloud_backends() catches and skips - so a backend with no
    # key configured is silently left out of the chain, not an error.
    # NOTE: deepseek_client.py and openrouter_client.py existed as fully
    # working clients but were never actually reachable from here - this
    # list previously stopped at gemini. Added below in the order their own
    # docstrings always described.
    _CLOUD_BACKEND_SPECS = [
        ("groq", "ai.cloud_models.groq_client", "get_ultron_client"),
        ("nvidia", "ai.cloud_models.nvidia_client", "get_nvidia_client"),
        ("deepseek", "ai.cloud_models.deepseek_client", "get_deepseek_client"),
        ("openrouter", "ai.cloud_models.openrouter_client", "get_openrouter_client"),
        ("xkiro", "ai.cloud_models.xkiro_client", "get_xkiro_client"),
        ("gemini", "ai.cloud_models.gemini_client", "get_gemini_client"),
    ]

    def __init__(self):
        self.history: List[Dict[str, str]] = []
        self._cloud_backends: Optional[List] = None  # lazy [(name, client), ...], built once
        self._local_manager = None  # lazy - avoids touching Ollama at import time

        self.mode: str = "unknown"  # last backend that actually answered
        self.last_switch_reason: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_cloud_provider: Optional[str] = None

        self.stats = {
            "cloud": {"calls": 0, "errors": 0, "total_latency": 0.0},
            "local": {"calls": 0, "errors": 0, "total_latency": 0.0},
        }

    # -- lazy backend construction -----------------------------------------
    def _get_cloud_backends(self) -> List:
        """Construct every cloud backend that has an API key configured,
        once, in fallback order (Groq -> NVIDIA -> DeepSeek -> OpenRouter ->
        xKiro -> Gemini). A backend that
        fails to construct (no key set) is logged once and skipped for the
        rest of the process - it does not get retried every turn."""
        if self._cloud_backends is not None:
            return self._cloud_backends

        backends = []
        for name, module_path, getter_name in self._CLOUD_BACKEND_SPECS:
            try:
                module = __import__(module_path, fromlist=[getter_name])
                client = getattr(module, getter_name)()
                client.conversation_history = self.history
                backends.append((name, client))
            except Exception as e:
                logger.info("%s cloud backend not configured (%s) - skipping.", name, e)

        if not backends:
            if AI_MODE == "cloud":
                logger.warning(
                    "No cloud AI backend is configured (Groq/NVIDIA/Gemini) - AI_MODE=cloud has no local fallback, so chat will error until .env is fixed and Ultron restarts."
                )
            else:
                logger.warning(
                    "No cloud AI backend is configured (Groq/NVIDIA/Gemini) - local-only until .env is fixed and Ultron restarts."
                )
        self._cloud_backends = backends
        return self._cloud_backends

    def _get_local_manager(self):
        if self._local_manager is None:
            from ai.local_models.manager import get_local_manager

            self._local_manager = get_local_manager()
            self._local_manager.conversation_history = self.history
        return self._local_manager

    # -- mode tracking / events ---------------------------------------------
    def _set_mode(self, new_mode: str, reason: str) -> None:
        if new_mode != self.mode:
            logger.info("AI mode: %s -> %s (%s)", self.mode, new_mode, reason)
            try:
                from core.events import get_event_bus

                get_event_bus().emit("ai_mode_switch", from_mode=self.mode, to_mode=new_mode, reason=reason)
            except Exception:
                from core.error_trace import log_swallowed as _lsw

                _lsw("ai.ai_router._set_mode")
        self.mode = new_mode
        self.last_switch_reason = reason

    def _record(self, backend: str, latency: float, error: bool) -> None:
        s = self.stats[backend]
        s["calls"] += 1
        s["total_latency"] += latency
        if error:
            s["errors"] += 1

    # -- backend attempts -----------------------------------------------------
    def _attempt_cloud(self, user_message: str, tool_callback: Optional[Callable]) -> Optional[str]:
        """Try every configured cloud backend in order (Groq -> NVIDIA ->
        Gemini), with a short retry on transient failures within each one
        before moving to the next. Returns the reply string on success, or
        None if every cloud backend failed for this turn (caller falls back
        to local)."""
        backends = self._get_cloud_backends()
        if not backends:
            return None

        attempts = CLOUD_MAX_RETRIES + 1
        for name, client in backends:
            client.conversation_history = self.history  # keep pointed at shared history
            for attempt in range(1, attempts + 1):
                start = time.monotonic()
                try:
                    response = client.chat_with_tools(user_message, tool_callback)
                    latency = time.monotonic() - start
                    if _looks_like_cloud_failure(response):
                        self._record("cloud", latency, error=True)
                        self.last_error = f"{name}: {response}"
                        logger.info(
                            "%s returned a failure response (attempt %d/%d): %s", name, attempt, attempts, response
                        )
                        if attempt < attempts:
                            time.sleep(CLOUD_RETRY_BACKOFF_SECONDS)
                            continue
                        break  # exhausted retries on this backend - try the next one
                    self._record("cloud", latency, error=False)
                    self.last_cloud_provider = name
                    print(f"[AI: {name}] answered this turn ({latency:.1f}s)")
                    return response
                except Exception as e:
                    latency = time.monotonic() - start
                    self._record("cloud", latency, error=True)
                    self.last_error = f"{name}: {e}"
                    logger.info("%s raised (attempt %d/%d): %s", name, attempt, attempts, e)
                    if attempt < attempts:
                        time.sleep(CLOUD_RETRY_BACKOFF_SECONDS)
                        continue
                    break  # exhausted retries on this backend - try the next one
        return None

    def _attempt_cloud_guarded(self, user_message: str, tool_callback: Optional[Callable]) -> Optional[str]:
        """Phase 26 (Security & Privacy): the actual entry point every
        chat_with_tools() cloud attempt now goes through instead of
        calling _attempt_cloud() directly. Screens `user_message` via
        security/privacy_guard.py first:
          - a BLOCK-category hit (credit card, API key) returns None here,
            same as any other cloud failure - chat_with_tools()'s existing
            fallback-to-local logic handles it with no changes needed.
          - an ANONYMIZE-category hit (email, phone, IP) sends the masked
            text to the cloud backend instead of the raw message, then
            restores the real values into whatever comes back before
            returning it.
        Fails open (logs and sends the original message unscreened) if
        privacy_guard itself errors, matching this codebase's existing
        "an optional safety layer degrades, it doesn't take down the
        assistant loop" philosophy used throughout core/ and proactive/."""
        try:
            from security.privacy_guard import get_privacy_guard

            guard = get_privacy_guard()
            screening = guard.screen_for_cloud(user_message)
        except Exception as e:
            logger.warning(f"privacy_guard unavailable, sending unscreened: {e}")
            return self._attempt_cloud(user_message, tool_callback)

        if not screening.get("allowed", True):
            self.last_error = f"privacy_guard: {screening.get('reason')}"
            logger.info(f"Cloud attempt skipped by privacy_guard: {screening.get('reason')}")
            return None

        outgoing = screening.get("text", user_message)
        response = self._attempt_cloud(outgoing, tool_callback)
        if response is not None and screening.get("mapping"):
            response = guard.restore_response(response, screening["mapping"])
        return response

    def _attempt_local(self, user_message: str, tool_callback: Optional[Callable]) -> Optional[str]:
        """Try local. Returns the reply string on success, or None if local
        should be considered unavailable for this turn."""
        manager = self._get_local_manager()
        if not manager.is_available():
            self.last_error = "Local AI (Ollama at its configured host) is not reachable."
            return None

        manager.conversation_history = self.history
        start = time.monotonic()
        try:
            response = manager.chat_with_tools(user_message, tool_callback)
            self._record("local", time.monotonic() - start, error=False)
            print(f"[AI: local/ollama] answered this turn ({time.monotonic() - start:.1f}s)")
            return response
        except Exception as e:
            self._record("local", time.monotonic() - start, error=True)
            self.last_error = str(e)
            logger.info("Local AI failed: %s", e)
            return None

    # -- public API (matches UltronGroqClient's shape) -----------------------
    def chat_with_tools(self, user_message: str, tool_callback: Optional[Callable] = None) -> str:
        # Forced modes - explicit debugging/testing paths, no fallback.
        if AI_MODE == "cloud":
            response = self._attempt_cloud_guarded(user_message, tool_callback)
            if response is not None:
                self._set_mode("cloud", "AI_MODE=cloud")
                return response
            return (
                f"Cloud AI is unavailable, Sir ({self.last_error or 'unknown error'}), and AI_MODE is forced to cloud."
            )

        if AI_MODE == "local":
            response = self._attempt_local(user_message, tool_callback)
            if response is not None:
                self._set_mode("local", "AI_MODE=local")
                return response
            return (
                f"Local AI is unavailable, Sir ({self.last_error or 'unknown error'}), and AI_MODE is forced to local."
            )

        # Auto mode - the normal path.
        online = is_online()

        if online:
            response = self._attempt_cloud_guarded(user_message, tool_callback)
            if response is not None:
                self._set_mode("cloud", "online")
                return response
            # Cloud failed even though we appear online - fall back to local.
            response = self._attempt_local(user_message, tool_callback)
            if response is not None:
                self._set_mode("local", "cloud failed, falling back")
                return response
            return (
                "I'm having trouble reaching both the cloud and the local AI right now, Sir "
                f"({self.last_error or 'unknown error'}). Please check your connection or Ollama, and try again."
            )

        # Offline - go straight to local.
        response = self._attempt_local(user_message, tool_callback)
        if response is not None:
            self._set_mode("local", "offline")
            return response
        return (
            "I'm offline and local AI isn't available either, Sir "
            f"({self.last_error or 'no local model reachable'}). "
            "Please check your internet connection, or start Ollama for offline use."
        )

    def chat(self, user_message: str) -> str:
        return self.chat_with_tools(user_message)

    def chat_fast_stream(self, user_message: str):
        """'Normal'-tier fast path for the low-latency pipeline
        (ai/complexity_router.py + core.assistant._handle_fast_tier). Only
        the Groq cloud backend has a small/fast streamed model wired up
        (see UltronGroqClient.chat_fast_stream) - forced local mode, being
        offline, or Groq not being configured all fall straight through by
        yielding nothing, exactly like chat_fast_stream's own error path,
        so callers only ever need one check: did anything come out at all.
        Deliberately no local/Ollama equivalent here - Ollama's own
        streaming would need its own tool-free prompt path, and the
        complexity/latency tradeoff that justifies this tier's existence
        for a fast cloud model doesn't obviously hold for a local one on
        typical hardware; that's a follow-up, not a silent regression, if
        someone wants it later.

        Same shared self.history as chat_with_tools - a fast-tier turn is
        still visible to the strong model on the next request."""
        if AI_MODE == "local":
            return
        if not is_online():
            return

        groq_client = None
        for name, client in self._get_cloud_backends():
            if name == "groq" and hasattr(client, "chat_fast_stream"):
                groq_client = client
                break
        if groq_client is None:
            return

        groq_client.conversation_history = self.history
        start = time.monotonic()
        got_any = False
        try:
            for chunk in groq_client.chat_fast_stream(user_message):
                got_any = True
                yield chunk
        except Exception as e:
            self.last_error = f"groq fast-tier: {e}"
            logger.info("Fast-tier stream raised: %s", e)
            return
        finally:
            latency = time.monotonic() - start
            self._record("cloud", latency, error=not got_any)
            if got_any:
                self.last_cloud_provider = "groq"
                self._set_mode("cloud", "fast-tier")
                print(f"[AI: groq/fast-tier] answered this turn ({latency:.1f}s)")

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Single-shot completion (no tools, no shared conversation history)
        for internal callers like ai/reasoning.py and ai/planning.py that
        need one prompt turned into text. Same online/offline + fallback
        policy as chat_with_tools, just without threading chat history or
        tool calls through it. Raises RuntimeError if nothing is available."""
        if AI_MODE != "local":
            for name, client in self._get_cloud_backends():
                start = time.monotonic()
                try:
                    text = client.complete_once(prompt, temperature=temperature, max_tokens=max_tokens)
                    self._record("cloud", time.monotonic() - start, error=False)
                    self._set_mode("cloud", "complete()")
                    self.last_cloud_provider = name
                    return text
                except Exception as e:
                    self._record("cloud", time.monotonic() - start, error=True)
                    self.last_error = f"{name}: {e}"
                    logger.info("%s complete_once failed: %s", name, e)
                    continue
            if AI_MODE == "cloud":
                raise RuntimeError(f"Cloud AI unavailable: {self.last_error or 'no cloud backend configured'}")

        manager = self._get_local_manager()
        if manager.is_available():
            start = time.monotonic()
            try:
                text = manager.complete_once(prompt, temperature=temperature, max_tokens=max_tokens)
                self._record("local", time.monotonic() - start, error=False)
                self._set_mode("local", "complete() fallback")
                return text
            except Exception as e:
                self._record("local", time.monotonic() - start, error=True)
                self.last_error = str(e)
                raise RuntimeError(f"Local AI unavailable: {e}") from e

        raise RuntimeError(self.last_error or "No AI backend (cloud or local) is available")

    def clear_history(self) -> None:
        self.history.clear()

    def get_history(self) -> List[Dict[str, str]]:
        return list(self.history)

    def get_status(self) -> Dict:
        """Live status for the dashboard: current mode, connectivity,
        which models are configured, and rolling performance stats."""

        def _avg(backend: str) -> float:
            s = self.stats[backend]
            return (s["total_latency"] / s["calls"]) if s["calls"] else 0.0

        return {
            "mode": self.mode,
            "online": is_online(),
            "cloud_model": MODEL_NAME,
            "local_model": OLLAMA_MODEL,
            "cloud_available": len(self._get_cloud_backends()) > 0,
            "cloud_backends": [name for name, _ in self._get_cloud_backends()],
            "last_cloud_provider": self.last_cloud_provider,
            "last_switch_reason": self.last_switch_reason,
            "last_error": self.last_error,
            "stats": {
                "cloud": {**self.stats["cloud"], "avg_latency": _avg("cloud")},
                "local": {**self.stats["local"], "avg_latency": _avg("local")},
            },
        }


_router: Optional[AIRouter] = None


def get_router() -> AIRouter:
    global _router
    if _router is None:
        _router = AIRouter()
    return _router
