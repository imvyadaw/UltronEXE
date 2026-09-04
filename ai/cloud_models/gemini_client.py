"""
Gemini Client with Tool Calling
================================
3rd link in the main tool-calling fallback chain: Groq -> NVIDIA -> Gemini
-> Ollama (see ai/ai_router.py). Only reached when both Groq and NVIDIA have
failed/rate-limited for this turn.

This is a DIFFERENT file from ai/llm/gemini_client.py - that one is a plain
text-completion-only client used by ai/llm/model_factory.py for internal,
no-tools callers (ai/planning.py, ai/reasoning.py, ...). This one speaks
Gemini's function-calling API so it can actually execute Ultron tools
(open apps, send messages, etc.), matching UltronGroqClient/UltronNvidiaClient's
public shape so ai_router.py can drive all three interchangeably.
"""

import requests
from typing import List, Dict, Optional

from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_TOKENS, TEMPERATURE, MAX_HISTORY_LENGTH
from ai.prompts import SYSTEM_PROMPT
from ai.tool_selector import select_tools_for_api
from ai.tool_runtime import execute_tool_from_dict

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = 60
MAX_TOOL_ROUNDS = 5

# Gemini's function-declaration JSON schema doesn't understand every key
# OpenAI-style parameter objects can carry (e.g. our "type": "number" is
# fine, but stray extras would be rejected) - keep only the keys Gemini's
# schema actually supports at each level.
_ALLOWED_SCHEMA_KEYS = {"type", "description", "properties", "required", "items", "enum"}


def _clean_schema(schema: Dict) -> Dict:
    if not isinstance(schema, dict):
        return schema
    out = {k: v for k, v in schema.items() if k in _ALLOWED_SCHEMA_KEYS}
    if "properties" in out and isinstance(out["properties"], dict):
        out["properties"] = {k: _clean_schema(v) for k, v in out["properties"].items()}
    if "items" in out and isinstance(out["items"], dict):
        out["items"] = _clean_schema(out["items"])
    return out


def _to_gemini_tools(openai_tools: List[Dict]) -> List[Dict]:
    """Convert our OpenAI/Groq-style TOOLS entries ({"type": "function",
    "function": {"name", "description", "parameters"}}) into Gemini's
    functionDeclarations format."""
    declarations = []
    for t in openai_tools:
        fn = t.get("function", t)
        params = _clean_schema(fn.get("parameters") or {"type": "object", "properties": {}})
        # Gemini rejects an empty "properties": {} object combined with a
        # non-empty "required" list, and dislikes a totally empty object -
        # normalize the empty-args case explicitly.
        if not params.get("properties"):
            params = {"type": "object", "properties": {}}
        declarations.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description", ""),
                "parameters": params,
            }
        )
    return declarations


class UltronGeminiClient:
    """Client for Gemini - same public shape as UltronGroqClient/
    UltronNvidiaClient so ai_router.py can drive it interchangeably."""

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found! Set it in .env to enable the Gemini fallback.")

        self.api_key = GEMINI_API_KEY
        self.model = GEMINI_MODEL
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt = SYSTEM_PROMPT

    @staticmethod
    def _classify_error(e: Exception) -> str:
        msg = str(e).lower()
        if "429" in msg or "rate limit" in msg or "quota" in msg:
            return "rate limit"
        if "401" in msg or "403" in msg or "api key" in msg:
            return "invalid API key"
        if "timeout" in msg or "timed out" in msg:
            return "timeout"
        if "connection" in msg or "network" in msg:
            return "network error"
        return "error"

    def _history_to_contents(self) -> List[Dict]:
        """Rebuild Gemini-format `contents` from the shared plain
        role/content history (same shared self.history list ai_router.py
        points every backend's conversation_history at)."""
        contents = []
        for m in self.conversation_history:
            role = m.get("role", "user")
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": m.get("content", "")}]})
        return contents

    def _post(self, contents: List[Dict], tools: Optional[List[Dict]], max_tokens: int, temperature: float) -> Dict:
        url = f"{_BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": self.system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if tools:
            payload["tools"] = [{"functionDeclarations": tools}]

        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise RuntimeError(f"Gemini request failed: {e}") from e

        if resp.status_code == 429:
            raise RuntimeError("Gemini free-tier rate limit hit.")
        if not resp.ok:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    @staticmethod
    def _extract_parts(data: Dict) -> List[Dict]:
        try:
            return data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError):
            reason = (data.get("candidates") or [{}])[0].get("finishReason", "unknown")
            raise RuntimeError(f"Gemini returned no usable content (finishReason={reason})")

    def _execute_tool_from_dict(self, tool_dict: Dict) -> str:
        return execute_tool_from_dict(tool_dict)

    def chat_with_tools(self, user_message: str, tool_callback=None) -> str:
        contents = self._history_to_contents()
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        selected_tools = _to_gemini_tools(select_tools_for_api(user_message))

        try:
            data = self._post(contents, selected_tools, MAX_TOKENS, TEMPERATURE)
            parts = self._extract_parts(data)
        except Exception as e:
            reason = self._classify_error(e)
            print(f"Model gemini/{self.model} failed ({reason}). Switching to next backend...")
            return f"Error: Gemini failed ({reason}): {e}"

        rounds = 0
        while rounds < MAX_TOOL_ROUNDS:
            function_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not function_calls:
                break
            rounds += 1

            # The model's turn (the function call request itself) must be
            # echoed back before our function response, per Gemini's protocol.
            contents.append({"role": "model", "parts": parts})

            response_parts = []
            for call in function_calls:
                tool_name = call.get("name")
                tool_args = call.get("args", {}) or {}

                if tool_callback:
                    tool_callback(tool_name, tool_args)

                result = self._execute_tool_from_dict({"tool": tool_name, **tool_args})
                response_parts.append(
                    {
                        "functionResponse": {
                            "name": tool_name,
                            "response": {"result": result},
                        }
                    }
                )
            contents.append({"role": "function", "parts": response_parts})

            try:
                data = self._post(contents, selected_tools, MAX_TOKENS, TEMPERATURE)
                parts = self._extract_parts(data)
            except Exception as e:
                return f"Error while processing the result ({self._classify_error(e)}): {e}"

        final_response = "".join(p.get("text", "") for p in parts).strip()
        self._update_history(user_message, final_response)
        return final_response

    def _update_history(self, user_message: str, assistant_response: str):
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": assistant_response})
        if len(self.conversation_history) > MAX_HISTORY_LENGTH * 2:
            self.conversation_history = self.conversation_history[-(MAX_HISTORY_LENGTH * 2) :]

    def chat(self, user_message: str) -> str:
        return self.chat_with_tools(user_message)

    def complete_once(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        data = self._post([{"role": "user", "parts": [{"text": prompt}]}], None, max_tokens, temperature)
        parts = self._extract_parts(data)
        return "".join(p.get("text", "") for p in parts).strip()

    def clear_history(self):
        self.conversation_history = []

    def get_history(self) -> List[Dict[str, str]]:
        return self.conversation_history.copy()


gemini_client: Optional["UltronGeminiClient"] = None


def get_gemini_client() -> UltronGeminiClient:
    global gemini_client
    if gemini_client is None:
        gemini_client = UltronGeminiClient()
    return gemini_client
