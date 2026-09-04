"""
Model router
============
Single entry point the rest of the app calls to get an LLM client.
get_client() now returns the hybrid AIRouter (ai/ai_router.py) - which
automatically picks cloud (Groq) or local (Ollama) per turn - instead of
a cloud-only client, so every caller (this module has historically been
imported directly by plugins like the Telegram bot) gets online/offline
fallback for free without needing to know the router exists.

core/brain.get_brain() is the newer, preferred way to get this same
object; this module is kept for backward compatibility with existing
imports (e.g. plugins/installed/telegram/telegram_bot.py).
"""

from ai.ai_router import AIRouter, get_router


def get_client() -> AIRouter:
    """Get the active AI client - the hybrid router, cloud+local combined."""
    return get_router()
