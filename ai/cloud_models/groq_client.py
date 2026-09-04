"""
Groq Client Manager with Tool Calling
=====================================
Handles all interactions with the Groq API for Ultron with system control capabilities.

Uses Groq's native function-calling (the `tools=` param), not text-based JSON
extraction - the model returns structured tool_calls directly, which is far
more reliable than asking it to emit a JSON blob in plain text and regexing
it back out. See ai/tools_schema.py for the tool definitions themselves.
"""
import logging

from groq import Groq
from typing import List, Dict, Optional
import json
import re
import time

from config import (
    GROQ_API_KEY,
    MAX_TOKENS,
    TEMPERATURE,
    TOP_P,
    MAX_HISTORY_LENGTH,
    MODEL_NAME,
    FALLBACK_MODELS,
    diagnose_env,
    FAST_MODEL_NAME,
    FAST_MODEL_MAX_TOKENS,
    FAST_MODEL_TEMPERATURE,
    FAST_MODEL_HISTORY_MESSAGES,
    GROQ_TIMEOUT,
    MODEL_RATE_LIMIT_COOLDOWN_SECONDS,
)
from ai.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_CONCISE
from ai.tools_schema import TOOLS
from ai.tool_selector import select_tools_for_api
from ai.tool_runtime import execute_tool_from_dict, run_tools_parallel
from ai import legacy_tool_call
from storage.cache.usage_tracker import UsageTracker
from hardening import guard_turn

MAX_TOOL_ROUNDS = 5  # safety cap on chained tool calls in a single turn

# Module-level (shared across every UltronGroqClient instance in this
# process) map of model name -> unix timestamp it's rate-limited until.
# Without this, chat_with_tools() re-tries MODEL_NAME first on every single
# turn even when it was rate-limited seconds ago, eating a full failed-call
# round trip (often 10-40s+ once the SDK's own retry/backoff is factored
# in) before falling through to a model that would actually answer -
# exactly what made repeated turns take 45-140s+ in practice.
_MODEL_COOLDOWNS: Dict[str, float] = {}


def _model_on_cooldown(model: str) -> bool:
    return time.time() < _MODEL_COOLDOWNS.get(model, 0)


def _set_model_cooldown(model: str, error_str: str) -> None:
    """Rate-limit a model for MODEL_RATE_LIMIT_COOLDOWN_SECONDS, or for the
    provider's own suggested wait time if the error message includes one
    (e.g. Groq's "Please try again in 12.4s")."""
    wait_seconds = MODEL_RATE_LIMIT_COOLDOWN_SECONDS
    match = re.search(r"[Pp]lease try again in\s+([0-9.]+)m?([0-9.]*)s", error_str)
    if match:
        try:
            if match.group(2):
                wait_seconds = max(wait_seconds, float(match.group(1)) * 60 + float(match.group(2)))
            else:
                wait_seconds = max(wait_seconds, float(match.group(1)))
        except ValueError:
            logging.getLogger(__name__).exception("Suppressed ValueError")
    _MODEL_COOLDOWNS[model] = time.time() + wait_seconds


class UltronGroqClient:
    """Client for Ultron with intelligent conversation and system control."""

    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError(f"GROQ_API_KEY not found! {diagnose_env()}")

        # timeout is what actually stops a dead network call from hanging
        # the whole terminal forever - see config.py for why this matters
        # on Windows specifically.
        #
        # BUG FIXED: max_retries was GROQ_MAX_RETRIES (2), which made the
        # SDK itself silently retry a failed call up to 2 more times
        # (with its own exponential backoff) *before* raising - on top of
        # this file's own 4-model fallback loop AND ai_router.py's own
        # per-backend retry loop (CLOUD_MAX_RETRIES). Three retry layers
        # stacked multiplicatively (4 models x up to 3 SDK attempts x 2
        # router attempts = up to 24 HTTP round-trips before ever falling
        # through to the next provider), which is what made switching
        # away from a failing backend feel so slow. The SDK layer is
        # redundant - model-fallback + router retry already cover
        # transient failures - so it's disabled here (max_retries=0) and
        # each call now fails fast onto the next model/backend instead.
        self.client = Groq(api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT, max_retries=0)
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = SYSTEM_PROMPT
        self.usage_tracker = UsageTracker()

    @staticmethod
    def _classify_error(e: Exception) -> str:
        """Best-effort human-readable reason a model call failed, for logging."""
        msg = str(e).lower()
        status = getattr(e, "status_code", None)
        if status == 429 or "rate limit" in msg or "429" in msg:
            return "rate limit"
        if status == 401 or "unauthorized" in msg or "invalid api key" in msg or "401" in msg:
            return "invalid API key"
        if status == 404 or "not found" in msg or "decommissioned" in msg:
            return "model unavailable"
        if (
            status == 413
            or "413" in msg
            or "context_length_exceeded" in msg
            or "context length" in msg
            or "too large" in msg
            or "maximum context" in msg
            or "request too large" in msg
        ):
            return "payload/context too large"
        if "timeout" in msg or "timed out" in msg:
            return "timeout"
        if "connection" in msg or "network" in msg or "not in allowlist" in msg:
            return "network error"
        return "error"

    def _build_messages(self, user_message: str) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _build_fast_messages(self, user_message: str) -> List[Dict[str, str]]:
        """Lighter message list for chat_fast_stream()'s tool-free tier -
        SYSTEM_PROMPT_CONCISE (a few hundred tokens) instead of the full
        tool-calling SYSTEM_PROMPT (which spends most of its length on tool-
        usage rules that don't apply here, since no tools are ever attached
        to this call), and only the last FAST_MODEL_HISTORY_MESSAGES entries
        of conversation_history instead of the full MAX_HISTORY_LENGTH*2
        window _build_messages() sends the strong model.

        This only trims what gets SENT to the fast model for this one call -
        it does not touch self.conversation_history itself, so the strong
        model still sees the complete conversation (including fast-tier
        turns) on the next chat_with_tools() call exactly as before. Purely
        a prompt-token/time-to-first-token cut for the tier whose entire
        reason to exist is speed."""
        messages = [{"role": "system", "content": SYSTEM_PROMPT_CONCISE}]
        if FAST_MODEL_HISTORY_MESSAGES > 0:
            messages.extend(self.conversation_history[-FAST_MODEL_HISTORY_MESSAGES:])
        messages.append({"role": "user", "content": user_message})
        return messages

    def _update_history(self, user_message: str, assistant_response: str):
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_response})

        if len(self.conversation_history) > MAX_HISTORY_LENGTH * 2:
            self.conversation_history = self.conversation_history[-(MAX_HISTORY_LENGTH * 2) :]

    def _track_usage(self, model: Optional[str], usage) -> None:
        if not model or not usage:
            return
        tokens = (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
        self.usage_tracker.increment_usage(model, tokens)

    def _execute_tool_from_dict(self, tool_dict: Dict) -> str:
        """Execute a tool from a {"tool": name, **args} dictionary.
        Delegates to the shared ai/tool_runtime module (same dispatch used
        by the local/offline AI backend) so the mapping only lives once."""
        return execute_tool_from_dict(tool_dict)

    @staticmethod
    def _parse_tool_result(result: str) -> Dict:
        """Best-effort parse of a tool's JSON-string result into a dict,
        for hardening's hardening pipeline (result_normalizer.py
        handles both dicts and strings fine, but keeping this parse means
        turn_tool_results already matches the shape earlier code expects
        too). Never raises - an unparseable result is reported as itself so
        downstream still has *something* to compare against."""
        if isinstance(result, dict):
            return result
        try:
            parsed = json.loads(result)
            return parsed if isinstance(parsed, dict) else {"result": parsed}
        except (TypeError, ValueError):
            return {"result": result}

    def _call_model(self, model: str, messages: List[Dict], tools: List[Dict] = None):
        """Single completion call with tools attached. `tools` defaults to
        the full 644-tool TOOLS list only if the caller doesn't pass a
        (much smaller) pre-selected subset - see select_tools_for_api()
        in ai/tool_selector.py, used by chat_with_tools() below."""
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_TOKENS,
            top_p=TOP_P,
            tools=tools if tools is not None else TOOLS,
            tool_choice="auto",
        )

    def chat_fast_stream(self, user_message: str):
        """'Normal' tier of the low-latency pipeline (ai/complexity_router.py
        decides who gets routed here). Streams FAST_MODEL_NAME's reply as
        raw text deltas with NO tools attached at all - this is deliberately
        not a smaller tool-calling loop, just a plain streamed completion,
        since the whole point is skipping the tool round-trip latency for
        turns that don't need one. ai/complexity_router.classify() is the
        thing responsible for keeping tool-needing requests out of this
        path; this method doesn't re-check that itself.

        A generator - yields text chunks as they arrive so the caller (see
        UltronVoice.speak_stream in voice/tts/tts_engine.py) can start
        speaking sentence 1 while the model is still generating sentence 3.
        Never raises past the caller: any failure is logged and the
        generator simply ends (possibly having yielded nothing, possibly
        partway through a reply) - core.assistant.Assistant._handle_fast_tier
        falls back to the full chat_with_tools() pipeline when nothing at
        all came through.

        conversation_history is updated with the full accumulated reply on
        a clean finish, same as chat_with_tools/_update_history, so the
        strong model still has this turn in context on the next one.

        Uses _build_fast_messages() (SYSTEM_PROMPT_CONCISE + a short recent-
        history window), not _build_messages() - the full tool-calling
        SYSTEM_PROMPT and the strong model's whole history window are both
        unnecessary prompt weight here and were adding to this tier's
        time-to-first-token for no benefit, since this call never has tools
        attached anyway."""
        messages = self._build_fast_messages(user_message)
        collected = []
        try:
            stream = self.client.chat.completions.create(
                model=FAST_MODEL_NAME,
                messages=messages,
                temperature=FAST_MODEL_TEMPERATURE,
                max_completion_tokens=FAST_MODEL_MAX_TOKENS,
                top_p=TOP_P,
                stream=True,
            )
            for event in stream:
                delta = event.choices[0].delta.content if event.choices else None
                if delta:
                    collected.append(delta)
                    yield delta
        except Exception as e:
            logger_name = self._classify_error(e)
            print(f"[fast-tier stream error: {logger_name}] {e}")
            return
        finally:
            full = "".join(collected)
            if full.strip():
                self._update_history(user_message, full)

    def chat_with_tools(self, user_message: str, tool_callback=None) -> str:
        """Chat with native tool-calling support, falling back across models
        and (for models that don't return structured tool_calls) falling
        back to the legacy text-JSON extraction for a single turn."""
        messages = self._build_messages(user_message)

        # Picked once per turn - a small, relevant subset of the 644-tool
        # list instead of all of it, on every call this turn makes
        # (initial + fallback models + tool-result follow-up rounds).
        # See ai/tool_selector.py::select_tools_for_api for the ranking
        # and the fallback-to-everything behavior on an odd/ambiguous
        # message.
        selected_tools = select_tools_for_api(user_message)

        models_to_try = [MODEL_NAME] + FALLBACK_MODELS
        completion = None
        last_error = None
        used_model = None

        # Skip models still on a rate-limit cooldown from a previous turn.
        # If that would skip every model (all recently rate-limited), fall
        # back to trying the full list anyway - a stale/incorrect cooldown
        # shouldn't be able to make the assistant refuse to even attempt a
        # call.
        candidates = [m for m in models_to_try if not _model_on_cooldown(m)]
        if not candidates:
            candidates = models_to_try

        for model in candidates:
            try:
                completion = self._call_model(model, messages, selected_tools)
                used_model = model
                break
            except Exception as e:
                last_error = e
                reason = self._classify_error(e)
                if reason == "rate limit":
                    _set_model_cooldown(model, str(e))
                print(f"Model {model} failed ({reason}). Switching to next model...")
                continue

        if not completion:
            error_str = str(last_error)
            wait_match = re.search(r"Please try again in\s+([0-9ms\.]+)", error_str)
            if wait_match:
                wait_time = wait_match.group(1)
                return f"I have hit my rate limit on all safe channels, Sir. I am sleeping for {wait_time} to recharge. Please stand by."

            return f"Error: All models failed. Last error: {error_str}"

        self._track_usage(used_model, completion.usage)
        message = completion.choices[0].message

        # PHASE 29-B: name + arguments + parsed result of every tool call
        # this turn, so the hardening pipeline (Result Normalizer ->
        # Evidence Collector -> Verification Engine -> Truth Gate) below
        # has something to build evidence from and compare the final
        # response text against. See hardening/.
        turn_tool_names: List[str] = []
        turn_tool_args: List[Dict] = []
        turn_tool_results: List[Dict] = []

        # --- Native tool-calling loop ---------------------------------
        rounds = 0
        while getattr(message, "tool_calls", None) and rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [tc.model_dump() for tc in message.tool_calls],
                }
            )

            # PHASE 30 - PERFORMANCE: parse every tool call in this round
            # first (cheap, sequential - just JSON parsing + the callback,
            # kept in original order so any UI/console echo of "calling
            # X..." still prints in the order the model asked), THEN
            # dispatch all of them concurrently via run_tools_parallel().
            # Previously this was a single `for tool_call in ...` loop that
            # called _execute_tool_from_dict() one at a time, so N tools in
            # one round cost sum(latency) instead of max(latency).
            parsed_calls = []
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_args = {}
                if tool_callback:
                    tool_callback(tool_name, tool_args)
                parsed_calls.append((tool_call, tool_name, tool_args))

            jobs = [
                (lambda tn=tool_name, ta=tool_args: self._execute_tool_from_dict({"tool": tn, **ta}))
                for (_tc, tool_name, tool_args) in parsed_calls
            ]
            results = run_tools_parallel(jobs)

            for (tool_call, tool_name, tool_args), result in zip(parsed_calls, results):
                turn_tool_names.append(tool_name)
                turn_tool_args.append(tool_args)
                turn_tool_results.append(self._parse_tool_result(result))

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result,
                    }
                )

            try:
                completion = self._call_model(used_model, messages, selected_tools)
            except Exception as e:
                return f"Error while processing the result ({self._classify_error(e)}): {e}"

            self._track_usage(used_model, completion.usage)
            message = completion.choices[0].message

        final_response = message.content or ""

        # --- Legacy fallback: model replied in plain text with a tool call
        # instead of using native tool_calls - either a JSON blob, or (seen
        # from smaller Groq models like llama-3.1-8b-instant) Meta's raw
        # Llama-3.1 <function=name>{...}</function> text template. Only
        # checked when no native tool_calls were ever returned this turn.
        # split_at_tool_call() also drops anything the model wrote AFTER
        # the tag - models that fall back to this text format often keep
        # going and fabricate an "answer" instead of waiting for the real
        # tool result, so that trailing text must never reach the user or
        # get stored in history as if it were true. ----------------------
        if rounds == 0:
            legacy_call = legacy_tool_call.extract(final_response)
            if legacy_call:
                tool_name = legacy_call.get("tool", "unknown")
                if tool_callback:
                    tool_callback(tool_name, {k: v for k, v in legacy_call.items() if k != "tool"})

                result = self._execute_tool_from_dict(legacy_call)
                turn_tool_names.append(tool_name)
                turn_tool_args.append({k: v for k, v in legacy_call.items() if k != "tool"})
                turn_tool_results.append(self._parse_tool_result(result))
                visible_text, _ = legacy_tool_call.split_at_tool_call(final_response)
                messages.append({"role": "assistant", "content": visible_text})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Result:\n{result}\n\nRespond naturally and briefly based on this result. Don't explain tools or processes.",
                    }
                )
                try:
                    completion = self._call_model(used_model, messages, tools=[])
                    self._track_usage(used_model, completion.usage)
                    final_response = completion.choices[0].message.content or ""
                except Exception as e:
                    final_response = f"Error while processing the result ({self._classify_error(e)}): {e}"

        # PHASE 29-B: advisory, non-blocking hardening pass - Result
        # Normalizer -> Evidence Collector -> Verification Engine -> Truth
        # Gate (which itself still runs 29-A's regex-based check_turn() as
        # one of its two signals) - over final_response vs. what the tools
        # actually reported this turn. Logs a warning on mismatch, never
        # alters or withholds the response. guard_turn() already never
        # raises internally, but the try/except stays as an outer safety
        # net regardless. See hardening/.
        try:
            guard_turn(final_response, turn_tool_names, turn_tool_args, turn_tool_results)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ai.cloud_models.groq_client.chat_with_tools")

        self._update_history(user_message, final_response)
        return final_response

    def chat(self, user_message: str) -> str:
        """Simple chat."""
        return self.chat_with_tools(user_message)

    def complete_once(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Single-shot completion with no tools and no conversation history -
        for internal callers (ai/reasoning.py, ai/planning.py) that just need
        one prompt turned into text, not a full tool-calling turn. Raises on
        failure so ai/ai_router.py can catch it and fall back to local."""
        completion = self.client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        self._track_usage(MODEL_NAME, completion.usage)
        return (completion.choices[0].message.content or "").strip()

    def clear_history(self):
        self.conversation_history = []

    def get_history(self) -> List[Dict[str, str]]:
        return self.conversation_history.copy()


ultron_client: Optional["UltronGroqClient"] = None


def get_ultron_client() -> UltronGroqClient:
    global ultron_client
    if ultron_client is None:
        ultron_client = UltronGroqClient()
    return ultron_client
