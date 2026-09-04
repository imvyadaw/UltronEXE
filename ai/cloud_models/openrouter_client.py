"""
OpenRouter Client with Tool Calling
====================================
Link in the cloud tool-calling fallback chain: Groq -> NVIDIA -> DeepSeek ->
OpenRouter -> Gemini -> Ollama (see ai/ai_router.py). Only reached when every
backend before it has failed/rate-limited for this turn.

openrouter.ai exposes an OpenAI-compatible /v1/chat/completions endpoint that
proxies many providers - several of them (suffixed ":free" in the model id)
genuinely cost nothing, just rate-limited per-model. Because free models get
squeezed under load and occasionally 429 individually, this client tries its
own small list of free models in order (config.OPENROUTER_MODEL then
OPENROUTER_FALLBACK_MODELS) before giving up, the same way groq_client.py
tries multiple Groq models.
"""

from openai import OpenAI
from typing import List, Dict, Optional
import json

from config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_FALLBACK_MODELS,
    OPENROUTER_SITE_URL,
    OPENROUTER_APP_NAME,
    MAX_TOKENS,
    TEMPERATURE,
    TOP_P,
    MAX_HISTORY_LENGTH,
    CLOUD_CLIENT_TIMEOUT_SECONDS,
)
from ai.prompts import SYSTEM_PROMPT
from ai.tool_selector import select_tools_for_api
from ai.tool_runtime import execute_tool_from_dict, run_tools_parallel
from ai import legacy_tool_call

MAX_TOOL_ROUNDS = 5  # safety cap on chained tool calls in a single turn, same as groq_client.py


class UltronOpenRouterClient:
    """Client for OpenRouter (openrouter.ai) - same public shape as
    UltronGroqClient/UltronNvidiaClient so ai_router.py can drive any of
    them interchangeably."""

    def __init__(self):
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY not found! Set it in .env to enable the OpenRouter fallback.")

        # BUG FIXED: no timeout/max_retries meant the OpenAI SDK's own
        # defaults applied (10-minute timeout, 2 internal retries) - see
        # config.CLOUD_CLIENT_TIMEOUT_SECONDS for why this now fails fast.
        self.client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
            timeout=CLOUD_CLIENT_TIMEOUT_SECONDS,
            max_retries=0,
        )
        # OpenRouter recommends (not strictly requires) these for routing/
        # rate-limit attribution on their dashboard - harmless to omit but
        # cheap to include.
        self._extra_headers = {
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        }
        self.models_to_try = [OPENROUTER_MODEL] + OPENROUTER_FALLBACK_MODELS
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = SYSTEM_PROMPT

    @staticmethod
    def _classify_error(e: Exception) -> str:
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

    def _update_history(self, user_message: str, assistant_response: str):
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_response})
        if len(self.conversation_history) > MAX_HISTORY_LENGTH * 2:
            self.conversation_history = self.conversation_history[-(MAX_HISTORY_LENGTH * 2) :]

    def _execute_tool_from_dict(self, tool_dict: Dict) -> str:
        return execute_tool_from_dict(tool_dict)

    def _call_model(self, model: str, messages: List[Dict], tools: List[Dict]):
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            max_tokens=MAX_TOKENS,
            tools=tools,
            tool_choice="auto",
            stream=False,
            extra_headers=self._extra_headers,
        )

    def chat_with_tools(self, user_message: str, tool_callback=None) -> str:
        messages = self._build_messages(user_message)
        selected_tools = select_tools_for_api(user_message)

        completion = None
        last_error = None
        used_model = None
        for model in self.models_to_try:
            try:
                completion = self._call_model(model, messages, selected_tools)
                used_model = model
                break
            except Exception as e:
                last_error = e
                print(f"OpenRouter model {model} failed ({self._classify_error(e)}). Trying next free model...")
                continue

        if not completion:
            return f"Error: All OpenRouter models failed. Last error: {last_error}"

        message = completion.choices[0].message

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

            # PHASE 30 - PERFORMANCE: dispatch every tool call this round
            # concurrently instead of one-by-one - see the note in
            # ai/tool_runtime.py::run_tools_parallel for why this is safe.
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
            message = completion.choices[0].message

        final_response = message.content or ""

        # Legacy fallback: model replied in plain text with a tool call
        # instead of using native tool_calls - either a JSON blob, or (seen
        # from weaker/smaller fallback models) Meta's raw Llama-3.1
        # <function=name>{...}</function> text template, which some models
        # leak into content along with a FABRICATED "answer" instead of
        # waiting for the real tool result. split_at_tool_call() drops that
        # fabricated trailing text so it never reaches the user or history.
        if rounds == 0:
            legacy_call = legacy_tool_call.extract(final_response)
            if legacy_call:
                tool_name = legacy_call.get("tool", "unknown")
                if tool_callback:
                    tool_callback(tool_name, {k: v for k, v in legacy_call.items() if k != "tool"})
                result = self._execute_tool_from_dict(legacy_call)
                visible_text, _ = legacy_tool_call.split_at_tool_call(final_response)
                messages.append({"role": "assistant", "content": visible_text})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Result:\n{result}\n\nRespond naturally and briefly based on this result. Don't explain tools or processes.",
                    }
                )
                try:
                    completion = self._call_model(used_model, messages, [])
                    final_response = completion.choices[0].message.content or ""
                except Exception as e:
                    final_response = f"Error while processing the result ({self._classify_error(e)}): {e}"

        self._update_history(user_message, final_response)
        return final_response

    def chat(self, user_message: str) -> str:
        return self.chat_with_tools(user_message)

    def complete_once(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        last_error = None
        for model in self.models_to_try:
            try:
                completion = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    extra_headers=self._extra_headers,
                )
                return (completion.choices[0].message.content or "").strip()
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(f"All OpenRouter models failed: {last_error}")

    def clear_history(self):
        self.conversation_history = []

    def get_history(self) -> List[Dict[str, str]]:
        return self.conversation_history.copy()


openrouter_client: Optional["UltronOpenRouterClient"] = None


def get_openrouter_client() -> UltronOpenRouterClient:
    global openrouter_client
    if openrouter_client is None:
        openrouter_client = UltronOpenRouterClient()
    return openrouter_client
