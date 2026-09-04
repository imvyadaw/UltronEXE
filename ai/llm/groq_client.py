"""Groq client (ai/llm/)
======================
🆓 Groq free tier (llama-3.1/3.3, openai/gpt-oss, ...) - fastest inference
of the four providers, and the primary backend for Ultron's real
tool-calling conversation (see ai/cloud_models/groq_client.py, which this
module wraps rather than duplicates).

Do NOT reimplement the Groq SDK call here. This class exists so
ai/llm/model_factory.py can offer Groq through the same plain-text
BaseLLMClient interface as the other three free providers, for callers
(ai/planning.py, ai/reasoning.py, ai/multi_agent.py, ...) that just want
"give me a completion from whatever free model is available" without
caring which provider answered.
"""

from typing import Dict, List

from config import GROQ_API_KEY, MODEL_NAME
from ai.llm.base_client import BaseLLMClient


class GroqLLMClient(BaseLLMClient):
    name = "groq"

    def __init__(self):
        self._client = None  # lazy - constructing UltronGroqClient needs a valid key

    def is_available(self) -> bool:
        return bool(GROQ_API_KEY)

    def _get_client(self):
        if self._client is None:
            from ai.cloud_models.groq_client import get_ultron_client

            self._client = get_ultron_client()
        return self._client

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        if not self.is_available():
            raise RuntimeError("Groq is not configured (GROQ_API_KEY missing).")
        return self._get_client().complete_once(prompt, temperature=temperature, max_tokens=max_tokens)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Uses Groq's real chat_with_tools path (tools disabled here since
        this is the plain-text ai/llm/ interface) so multi-turn context is
        handled natively instead of flattened into one prompt string."""
        if not self.is_available():
            raise RuntimeError("Groq is not configured (GROQ_API_KEY missing).")
        client = self._get_client()
        # Replay all-but-last messages into history, then send the last
        # user turn through the normal chat path.
        history = [m for m in messages if m.get("role") in ("user", "assistant")]
        if not history:
            return ""
        *prior, last = history
        client.conversation_history = prior
        return client.chat(last.get("content", ""))

    @property
    def model_name(self) -> str:
        return MODEL_NAME
