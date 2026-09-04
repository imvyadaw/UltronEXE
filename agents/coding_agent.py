"""
Coding agent
============
A specialized agent for code-writing/editing/review, as opposed to the
general-purpose conversational agents/assistant_agent.py: no tool-calling loop,
no conversation history, no personality prompt - just a focused system
prompt per task and a direct call to Groq, since code generation wants a
clean context rather than the assistant's chat history bleeding in.
"""

from typing import Dict, Optional

from config import GROQ_API_KEY, MODEL_NAME
from agents.base_agent import BaseAgent
from stability.lazy_loader import lazy_attr

# PHASE 29-A stability fix: `from groq import Groq` used to sit at module
# level here, which meant `import windows` (done unconditionally by
# core/executor.py for every tool call) always imported the Groq SDK too -
# even for tool calls that never touch coding_agent. Deferred to first use
# in __init__ instead; see stability/lazy_loader.py.
_get_Groq = lazy_attr("groq", "Groq")

_CODE_SYSTEM_PROMPT = (
    "You are a precise, expert coding assistant. Output clean, correct, "
    "idiomatic code. When asked to write code, respond with the code in a "
    "single fenced code block and nothing else, unless explicitly asked to "
    "also explain it. Don't pad with disclaimers."
)


class CodingAgent(BaseAgent):
    """Write, explain, review, and fix code via a focused Groq prompt."""

    capabilities = ["code", "coding", "programming", "debugging"]

    def __init__(self):
        super().__init__("coding", "Focused code write/explain/review/fix agent")
        self._client = None
        if GROQ_API_KEY:
            try:
                self._client = _get_Groq()(api_key=GROQ_API_KEY)
            except Exception:
                # groq not installed, or client construction failed - degrade
                # to the same "no client" state _ask() already handles below,
                # instead of raising out of __init__ (and therefore out of
                # windows/__init__.py's module import, per the docstring
                # above every tool call would otherwise pay for).
                self._client = None

    def _ask(self, user_prompt: str) -> Dict:
        if not self._client:
            return {
                "error": "coding agent unavailable - either GROQ_API_KEY is not "
                "set (see config.py's diagnose_env()) or the groq package "
                "isn't installed (pip install groq)"
            }
        try:
            response = self._client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": _CODE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
            )
            return {"result": response.choices[0].message.content}
        except Exception as e:
            return {"error": str(e)}

    def write_code(self, spec: str, language: Optional[str] = None) -> Dict:
        """Write code from a natural-language spec."""
        lang_hint = f" in {language}" if language else ""
        return self._ask(f"Write code{lang_hint} for the following:\n\n{spec}")

    def explain_code(self, code: str) -> Dict:
        """Explain what a piece of code does."""
        return self._ask(f"Explain what this code does, concisely:\n\n{code}")

    def review_code(self, code: str) -> Dict:
        """Review code for bugs, style issues, and improvements."""
        return self._ask(
            "Review this code for bugs, edge cases, and style issues. " f"List concrete, actionable points:\n\n{code}"
        )

    def fix_code(self, code: str, error_message: Optional[str] = None) -> Dict:
        """Fix a bug in code, optionally given the error/traceback it produced."""
        prompt = f"Fix the bug(s) in this code:\n\n{code}"
        if error_message:
            prompt += f"\n\nIt produces this error:\n{error_message}"
        prompt += "\n\nReturn the corrected code."
        return self._ask(prompt)
