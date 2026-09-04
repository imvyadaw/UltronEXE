"""
Assistant agent
================
The main conversational agent - thin wrapper tying core/brain.py (LLM +
tool calling) and core/executor.py (tool dispatch) together for whatever
front-end is driving it (core.assistant.Assistant's CLI loop, or a
plugin like Telegram).

This used to live at agents/assistant.py; it moved here to match the
rest of agents/*_agent.py's naming. agents/assistant.py re-exports
AssistantAgent from this module so nothing that imported the old path
breaks.
"""

from agents.base_agent import BaseAgent
from core.brain import get_brain


class AssistantAgent(BaseAgent):
    capabilities = ["chat", "conversation", "general", "assistant"]

    def __init__(self):
        super().__init__("assistant", "General-purpose conversational agent (LLM + tool calling)")
        self.brain = get_brain()

    def handle(self, user_message: str, tool_callback=None) -> str:
        return self.brain.chat_with_tools(user_message, tool_callback)
