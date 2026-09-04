"""
Local AI Manager
================
Offline counterpart to ai/cloud_models/groq_client.UltronGroqClient -
same public shape (chat_with_tools / chat / clear_history / get_history /
conversation_history) so ai/ai_router.py can swap between cloud and local
without either backend or any downstream caller (agents/, plugins/,
main.py) knowing the difference.

Backend: a locally running Ollama server (see models/ollama/loader.py).
Model name comes from config.OLLAMA_MODEL - never hardcoded here, so
switching models is a .env edit, not a code change. Ollama itself is the
extension point for future local backends (llama.cpp, etc.) - swap what
this manager talks to without touching ai/ai_router.py or main.py.
"""

import json
from typing import Dict, List, Optional

from config import (
    OLLAMA_HOST,
    OLLAMA_MODEL,
    LOCAL_MAX_TOKENS,
    LOCAL_TEMPERATURE,
    LOCAL_CONTEXT_LENGTH,
    MAX_HISTORY_LENGTH,
)
from ai.prompts import SYSTEM_PROMPT
from ai.tool_selector import select_tools_for_api
from ai.tool_runtime import execute_tool_call, run_tools_parallel
from core.logger import get_logger
from models.ollama.loader import OllamaClient
from hardening import guard_turn

MAX_TOOL_ROUNDS = 5  # same cap as the cloud client, for the same reason

logger = get_logger("local_ai")


def _parse_tool_result(result) -> Dict:
    """Best-effort parse of a tool's JSON-string result into a dict, for
    hardening's hardening pipeline (result_normalizer.py handles
    both dicts and strings fine either way, but keeping this parse means
    turn_tool_results matches what ai/cloud_models/groq_client.py already
    passes). Never raises - an unparseable result is reported as itself so
    downstream still has *something* to compare against. Same helper as
    UltronGroqClient._parse_tool_result, duplicated here rather than shared
    since it's a two-line, dependency-free static method - not worth a new
    import just to avoid it."""
    if isinstance(result, dict):
        return result
    try:
        parsed = json.loads(result)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    except (TypeError, ValueError):
        return {"result": result}


class LocalAIManager:
    """Offline LLM chat + tool-calling, backed by a local Ollama server."""

    def __init__(self, host: str = None, model: str = None):
        self._client = OllamaClient(host=host or OLLAMA_HOST, model=model or OLLAMA_MODEL)
        self.model = model or OLLAMA_MODEL
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = SYSTEM_PROMPT
        self._tools_supported = True  # flips to False after the first HTTP
        # error from passing `tools=`, so we stop retrying a losing bet on
        # models that plainly don't support tool calling.

    # -- availability ------------------------------------------------------
    def is_available(self) -> bool:
        """Whether an Ollama server is reachable at all right now."""
        return self._client.is_available()

    def is_ready(self) -> bool:
        """Whether the server is reachable AND the configured model is
        actually pulled - the two distinct ways "local AI" can be unusable."""
        return self.is_available() and self._client.has_model(self.model)

    # -- history -------------------------------------------------------------
    def _build_messages(self, user_message: str) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _update_history(self, user_message: str, assistant_response: str) -> None:
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_response})
        if len(self.conversation_history) > MAX_HISTORY_LENGTH * 2:
            self.conversation_history = self.conversation_history[-(MAX_HISTORY_LENGTH * 2) :]

    def clear_history(self) -> None:
        self.conversation_history = []

    def get_history(self) -> List[Dict[str, str]]:
        return self.conversation_history.copy()

    # -- chat ----------------------------------------------------------------
    def chat_with_tools(self, user_message: str, tool_callback=None) -> str:
        """Same contract as UltronGroqClient.chat_with_tools: run the local
        model, execute any tool calls it makes via the shared tool runtime,
        feed results back, and return the final natural-language reply."""
        messages = self._build_messages(user_message)

        # Small relevant subset instead of the full 644-tool list - see
        # ai/tool_selector.py::select_tools_for_api. Matters even more
        # here than on the cloud path: local inference pays a much
        # higher per-token cost for a large prompt than Groq's LPUs do.
        selected_tools = select_tools_for_api(user_message)
        tools_arg = selected_tools if self._tools_supported else None
        result = self._client.chat(
            messages,
            model=self.model,
            temperature=LOCAL_TEMPERATURE,
            tools=tools_arg,
            max_tokens=LOCAL_MAX_TOKENS,
            num_ctx=LOCAL_CONTEXT_LENGTH,
        )

        if "error" in result and tools_arg is not None:
            # This model likely doesn't support tool calling - fall back to
            # a plain chat for the rest of this process's lifetime instead
            # of paying for a failed request every single turn.
            logger.info("Local model rejected tools=, retrying without tools: %s", result["error"])
            self._tools_supported = False
            result = self._client.chat(
                messages,
                model=self.model,
                temperature=LOCAL_TEMPERATURE,
                max_tokens=LOCAL_MAX_TOKENS,
                num_ctx=LOCAL_CONTEXT_LENGTH,
            )

        if "error" in result:
            raise RuntimeError(f"Local AI unavailable: {result['error']}")

        # PHASE 29-B: name + arguments + parsed result of every tool call
        # this turn, so the hardening pipeline below has something to build
        # evidence from and compare the final response text against - same
        # tracking ai/cloud_models/groq_client.py's chat_with_tools() does.
        # See hardening/.
        turn_tool_names: List[str] = []
        turn_tool_args: List[Dict] = []
        turn_tool_results: List[Dict] = []

        rounds = 0
        while result.get("tool_calls") and rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            tool_calls = result["tool_calls"]
            messages.append({"role": "assistant", "content": result.get("content", ""), "tool_calls": tool_calls})

            # PHASE 30 - PERFORMANCE: parse every tool call first (in
            # order, so the callback still echoes in the order the model
            # asked), then dispatch them all concurrently via
            # run_tools_parallel() instead of one-by-one - see the note in
            # ai/tool_runtime.py for why this is safe for I/O-bound tools.
            parsed_calls = []
            for tool_call in tool_calls:
                fn = tool_call.get("function", {})
                tool_name = fn.get("name")
                raw_args = fn.get("arguments", {})
                # Ollama returns arguments as a dict already (not a JSON
                # string like Groq's raw API) but be defensive either way.
                if isinstance(raw_args, str):
                    try:
                        tool_args = json.loads(raw_args or "{}")
                    except json.JSONDecodeError:
                        tool_args = {}
                else:
                    tool_args = raw_args or {}

                if tool_callback:
                    tool_callback(tool_name, tool_args)
                parsed_calls.append((tool_name, tool_args))

            jobs = [
                (lambda tn=tool_name, ta=tool_args: execute_tool_call(tn, ta))
                for (tool_name, tool_args) in parsed_calls
            ]
            tool_results = run_tools_parallel(jobs)

            for (tool_name, tool_args), tool_result in zip(parsed_calls, tool_results):
                turn_tool_names.append(tool_name)
                turn_tool_args.append(tool_args)
                turn_tool_results.append(_parse_tool_result(tool_result))
                messages.append({"role": "tool", "name": tool_name, "content": tool_result})

            result = self._client.chat(
                messages,
                model=self.model,
                temperature=LOCAL_TEMPERATURE,
                tools=selected_tools if self._tools_supported else None,
                max_tokens=LOCAL_MAX_TOKENS,
                num_ctx=LOCAL_CONTEXT_LENGTH,
            )
            if "error" in result:
                raise RuntimeError(f"Local AI unavailable mid-conversation: {result['error']}")

        final_response = result.get("content", "") or ""

        # PHASE 29-B: same advisory, non-blocking hardening pass the cloud
        # client runs - logs a warning on mismatch, never alters or
        # withholds the response. guard_turn() never raises internally, but
        # the try/except stays as an outer safety net regardless (a local-
        # only backend has one less reason than ever to fail a real turn
        # over a logging check). See hardening/.
        try:
            guard_turn(final_response, turn_tool_names, turn_tool_args, turn_tool_results)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("ai.local_models.manager.chat_with_tools")

        self._update_history(user_message, final_response)
        return final_response

    def chat(self, user_message: str) -> str:
        return self.chat_with_tools(user_message)

    def complete_once(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Single-shot completion with no tools and no conversation history -
        offline counterpart to UltronGroqClient.complete_once(). Raises on
        failure so ai/ai_router.py can report it clearly."""
        result = self._client.chat(
            [{"role": "user", "content": prompt}],
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            num_ctx=LOCAL_CONTEXT_LENGTH,
        )
        if "error" in result:
            raise RuntimeError(f"Local AI unavailable: {result['error']}")
        return (result.get("content", "") or "").strip()


_local_manager: Optional[LocalAIManager] = None


def get_local_manager() -> LocalAIManager:
    global _local_manager
    if _local_manager is None:
        _local_manager = LocalAIManager()
    return _local_manager
