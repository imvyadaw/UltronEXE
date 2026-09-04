"""
Conversation package (Phase 16)
================================
Multi-turn conversational plumbing specifically for proactive/
scenarios/ - "Ultron said something unprompted, now what does the user
mean by their reply". This is distinct from core/context.py (which
tracks active app/cwd/tool results for the main chat loop) and from
ai/ai_router.py's shared history (the raw LLM conversation transcript):
context_engine.py here tracks *proactive alerts and how the user
responded to them* specifically, so a scenario can tell "yes, remind me
in 10" from "no, dismiss" from an unrelated new request.

    context_engine.py   - rolling memory of recent proactive turns
    intent_analyzer.py  - classifies what a short reply to an alert means
    response_builder.py - assembles the final Ultron-voiced reply text
"""

from conversation.context_engine import ConversationContextEngine, get_context_engine
from conversation.intent_analyzer import IntentAnalyzer, get_intent_analyzer
from conversation.response_builder import ResponseBuilder, get_response_builder

__all__ = [
    "ConversationContextEngine",
    "get_context_engine",
    "IntentAnalyzer",
    "get_intent_analyzer",
    "ResponseBuilder",
    "get_response_builder",
]
