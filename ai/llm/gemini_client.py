"""Gemini client (ai/llm/)
========================
🆓 Google Gemini free tier (default model: gemini-1.5-flash - generous
free quota, no credit card required to start). Talks to the REST API
directly with `requests` (already a hard dependency of the project) so
this provider doesn't need the google-generativeai SDK installed.

Setup: set GEMINI_API_KEY in .env (get a free key at
https://aistudio.google.com/apikey). Optional GEMINI_MODEL overrides the
default model. See config.py.
"""

import requests
from typing import Dict, List

from config import GEMINI_API_KEY, GEMINI_MODEL
from ai.llm.base_client import BaseLLMClient

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_TIMEOUT = 30


class GeminiLLMClient(BaseLLMClient):
    name = "gemini"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _generate(self, contents: List[Dict], temperature: float, max_tokens: int) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini is not configured (GEMINI_API_KEY missing).")

        url = f"{_BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise RuntimeError(f"Gemini request failed: {e}") from e

        if resp.status_code == 429:
            raise RuntimeError("Gemini free-tier rate limit hit. Try again shortly.")
        if not resp.ok:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError) as e:
            # Most common cause: the prompt was blocked by safety filters.
            reason = data.get("candidates", [{}])[0].get("finishReason", "unknown")
            raise RuntimeError(f"Gemini returned no usable content (finishReason={reason}): {e}") from e

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        return self._generate([{"role": "user", "parts": [{"text": prompt}]}], temperature, max_tokens)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 400) -> str:
        contents = []
        for m in messages:
            role = m.get("role", "user")
            if role == "system":
                # Gemini has no "system" role in `contents`; fold it into
                # the first user turn instead of dropping it.
                contents.append({"role": "user", "parts": [{"text": f"(system instructions) {m.get('content', '')}"}]})
                continue
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": m.get("content", "")}]})
        return self._generate(contents, temperature, max_tokens)
