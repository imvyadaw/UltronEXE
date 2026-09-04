"""Base LLM client
================
Abstract interface every provider client under ai/llm/ implements
(groq_client.py, gemini_client.py, huggingface_client.py, ollama_client.py).

This is a *thin, provider-agnostic* layer on top of the already-working
production path (ai/ai_router.py + ai/cloud_models/groq_client.py +
ai/local_models/manager.py, which handle tool-calling and are what
core/brain.py actually talks to). ai/llm/ instead gives callers that just
need plain text completions - ai/planning.py, ai/reasoning.py,
ai/multi_agent.py, ai/rag_engine.py, ai/tool_selector.py - one uniform,
swappable interface across every FREE-tier provider Ultron can reach,
picked automatically by ai/llm/model_factory.py.

Every client exposes the same three things:
    - name           : short human-readable provider id, e.g. "groq"
    - is_available()  : cheap, no-network check of whether this client
                         *could* work right now (API key present, or a
                         local server reachable) - not a guarantee the
                         next call succeeds, just enough to skip a client
                         that plainly isn't configured.
    - complete(prompt) : single-shot text completion. Raises on failure -
                         callers (ai/llm/model_factory.py) catch and try
                         the next provider in priority order.
"""

from abc import ABC, abstractmethod
from typing import Dict, List


class BaseLLMClient(ABC):
    """Common interface for a FREE-tier LLM provider client."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap local check: is this client configured/reachable at all
        (API key set, or local server up)? Does not guarantee a live call
        will succeed - just enough to skip an unconfigured provider."""
        raise NotImplementedError

    @abstractmethod
    def complete(self, prompt: str, temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Single-shot text completion, no conversation history, no tools.
        Raises RuntimeError (or a provider-specific exception) on failure -
        callers are expected to catch and fall back to the next client."""
        raise NotImplementedError

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 400) -> str:
        """Multi-turn chat given a list of {"role", "content"} messages.
        Default implementation flattens history into a single prompt and
        calls complete() - providers with a real chat endpoint (Groq,
        Gemini) should override this for better results."""
        lines = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            prefix = "System" if role == "system" else ("Assistant" if role == "assistant" else "User")
            lines.append(f"{prefix}: {content}")
        lines.append("Assistant:")
        return self.complete("\n".join(lines), temperature=temperature, max_tokens=max_tokens)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} available={self.is_available()}>"
