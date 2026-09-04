"""Ollama client (ai/llm/)
========================
🆓 Ollama Local - fully offline, zero API key, zero rate limit, but needs
Ollama installed and a model pulled on this machine (see
models/ollama/loader.py). Lowest priority in ai/llm/model_factory.py's
default order since Groq/Gemini/HuggingFace are faster to set up (just an
API key, no local install), but it's the only option with no internet
dependency and no per-provider rate limit - and it's already the
production offline backend via ai/local_models/manager.py, which this
class wraps.
"""

from typing import Dict, List

from config import OLLAMA_MODEL
from ai.llm.base_client import BaseLLMClient


class OllamaLLMClient(BaseLLMClient):
    name = "ollama"

    def __init__(self):
        self._manager = None  # lazy - avoids touching Ollama at import time

    def _get_manager(self):
        if self._manager is None:
            from ai.local_models.manager import get_local_manager

            self._manager = get_local_manager()
        return self._manager

    def is_available(self) -> bool:
        try:
            return self._get_manager().is_ready()
        except Exception:
            return False

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        return self._get_manager().complete_once(prompt, temperature=temperature, max_tokens=max_tokens)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 400) -> str:
        manager = self._get_manager()
        history = [m for m in messages if m.get("role") in ("user", "assistant")]
        if not history:
            return ""
        *prior, last = history
        manager.conversation_history = prior
        return manager.chat(last.get("content", ""))

    @property
    def model_name(self) -> str:
        return OLLAMA_MODEL
