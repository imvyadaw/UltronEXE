"""
Assistant agent (back-compat path)
===================================
AssistantAgent now lives in agents/assistant_agent.py, matching the
agents/*_agent.py naming used by the rest of agents/. This module
re-exports it so any older import of `agents.assistant` keeps working.
"""

