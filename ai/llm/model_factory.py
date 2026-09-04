"""Model factory
==============
Auto-selects the best available FREE LLM provider from ai/llm/, in
priority order (config.FREE_MODEL_PRIORITY, default:
"groq,gemini,huggingface,ollama" - fastest/most reliable free tier
first, fully-offline Ollama last as the no-API-key-needed fallback).

This is a *convenience* layer for callers that just want one clean
`complete(prompt)` call and don't care which provider answers - e.g.
ai/planning.py, ai/reasoning.py, ai/chain_of_thought.py, ai/multi_agent.py,
ai/few_shot_learning.py, ai/rag_engine.py. It does NOT replace
ai/ai_router.py, which remains the production path for the main
tool-calling conversation (core/brain.py -> ai/router.get_client()) -
that router already has its own tuned cloud/local fallback and retry
policy and should keep being used for anything user-facing that needs
tool calls.

Usage:
    from ai.llm.model_factory import ModelFactory

    factory = ModelFactory()
    text = factory.complete("Summarize this in one sentence: ...")
    # or, to see which provider actually answered:
    result = factory.complete_with_provider("...")
    print(result["provider"], result["text"])
"""

from typing import Dict, List, Optional

from config import FREE_MODEL_PRIORITY
from core.logger import get_logger
from ai.llm.base_client import BaseLLMClient

logger = get_logger("model_factory")

_PROVIDER_BUILDERS = {
    "groq": lambda: __import__("ai.llm.groq_client", fromlist=["GroqLLMClient"]).GroqLLMClient(),
    "gemini": lambda: __import__("ai.llm.gemini_client", fromlist=["GeminiLLMClient"]).GeminiLLMClient(),
    "huggingface": lambda: __import__(
        "ai.llm.huggingface_client", fromlist=["HuggingFaceLLMClient"]
    ).HuggingFaceLLMClient(),
    "ollama": lambda: __import__("ai.llm.ollama_client", fromlist=["OllamaLLMClient"]).OllamaLLMClient(),
}


class ModelFactory:
    """Picks and calls the best currently-available free LLM provider."""

    def __init__(self, priority: Optional[List[str]] = None):
        names = priority or [p.strip() for p in FREE_MODEL_PRIORITY.split(",") if p.strip()]
        self._priority = [n for n in names if n in _PROVIDER_BUILDERS]
        self._clients: Dict[str, BaseLLMClient] = {}

    def _get_client(self, provider: str) -> BaseLLMClient:
        if provider not in self._clients:
            self._clients[provider] = _PROVIDER_BUILDERS[provider]()
        return self._clients[provider]

    def available_providers(self) -> List[str]:
        """Every configured provider, in priority order, that reports
        itself available right now (has an API key / local server up)."""
        out = []
        for name in self._priority:
            try:
                if self._get_client(name).is_available():
                    out.append(name)
            except Exception as e:
                logger.debug("Provider %s availability check raised: %s", name, e)
        return out

    def best_available(self) -> Optional[BaseLLMClient]:
        """The highest-priority provider that's currently available, or
        None if nothing is configured at all."""
        for name in self._priority:
            try:
                client = self._get_client(name)
                if client.is_available():
                    return client
            except Exception as e:
                logger.debug("Provider %s construction/check raised: %s", name, e)
        return None

    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Try each provider in priority order until one succeeds. Raises
        RuntimeError only if every configured provider failed or none are
        configured at all."""
        result = self.complete_with_provider(prompt, temperature, max_tokens)
        return result["text"]

    def complete_with_provider(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> Dict:
        """Same as complete(), but also returns which provider answered -
        useful for logging/debugging which free tier is actually serving
        a given request."""
        errors = {}
        for name in self._priority:
            try:
                client = self._get_client(name)
                if not client.is_available():
                    continue
                text = client.complete(prompt, temperature=temperature, max_tokens=max_tokens)
                return {"provider": name, "text": text}
            except Exception as e:
                logger.info("Free model provider '%s' failed, trying next: %s", name, e)
                errors[name] = str(e)

        if not errors and not self.available_providers():
            raise RuntimeError(
                "No free LLM provider is configured. Set at least one of GROQ_API_KEY, "
                "GEMINI_API_KEY, HUGGINGFACE_API_KEY in .env, or run a local Ollama server."
            )
        raise RuntimeError(f"All configured free LLM providers failed: {errors}")

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Same priority-order fallback as complete(), but for multi-turn
        chat (list of {"role", "content"} messages)."""
        errors = {}
        for name in self._priority:
            try:
                client = self._get_client(name)
                if not client.is_available():
                    continue
                return client.chat(messages, temperature=temperature, max_tokens=max_tokens)
            except Exception as e:
                logger.info("Free model provider '%s' failed on chat(), trying next: %s", name, e)
                errors[name] = str(e)
        raise RuntimeError(f"All configured free LLM providers failed: {errors}")


_factory: Optional[ModelFactory] = None


def get_model_factory() -> ModelFactory:
    """Process-wide singleton, mirroring ai/ai_router.get_router()."""
    global _factory
    if _factory is None:
        _factory = ModelFactory()
    return _factory
