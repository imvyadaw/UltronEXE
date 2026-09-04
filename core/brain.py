"""
Brain
=====
Top-level orchestrator: main.py talks to this, not directly to ai/router.
get_brain() now returns the AIRouter (ai/ai_router.py), which transparently
picks cloud (Groq) or local (Ollama) per turn - online/offline detection,
fallback, and retry all happen inside the router. Every caller here
(main.py, agents/assistant_agent.py, plugins/) only ever needs .chat_with_tools()
/ .chat() / .clear_history() / .get_history(), which the router exposes
with the exact same shape the old cloud-only client had, so nothing
downstream had to change.

This is also the seam where core/planner.py + core/context.py +
core/memory.py plug in once they're wired up, so main.py never has to
change for that either.
"""

from ai.ai_router import AIRouter, get_router


def get_brain() -> AIRouter:
    """Get the assistant's active 'brain' - the hybrid AI Router, which
    picks cloud or local per turn."""
    return get_router()
