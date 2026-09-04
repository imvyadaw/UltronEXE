"""
Writer Agent
============
Drafts and rewrites natural-language content - emails, messages,
short reports, social posts. It only produces text; it never sends,
posts, or saves anything itself. That's a deliberate line: getting a
draft to its destination is already covered by apps/communication/*.py
(whatsapp.py, slack.py, discord.py, ...) from Phase 6, and this agent
staying text-in/text-out means the same draft() call works whether the
caller's next step is a WhatsApp message, a Slack post, or a file on
disk - the destination is the caller's decision, not this module's.

Same lazy-import, None-on-failure contract as coder.py's
_call_brain() - see that module's docstring for the reasoning. This
file duplicates rather than imports that helper, matching
PHASE_18_5_SEARCH_ENGINE's own style of each module owning its full
request path rather than sharing a base client class.
"""

from typing import Dict, List, Optional


class WriterAgent:
    """LLM-backed content drafting/rewriting. Use get_writer()."""

    def is_available(self) -> bool:
        return self._call_brain("ping", "ping") is not None

    def draft(self, task: str, tone: str = "neutral", length: str = "medium") -> Dict:
        """Drafts content for `task`. `tone` is a free-form
        descriptor (e.g. "formal", "casual", "persuasive"); `length`
        is one of "short", "medium", "long" and is a hint, not a hard
        limit. Returns
        {"success": bool, "text": str, "error": Optional[str]}."""
        if not task:
            return {"success": False, "text": "", "error": "no task given"}
        system_prompt = (
            f"You are a writing assistant. Write in a {tone} tone, "
            f"aiming for {length} length. Reply with the finished "
            f"content only - no preamble, no explanation of what you wrote."
        )
        output = self._call_brain(system_prompt, task)
        if output is None:
            return {"success": False, "text": "", "error": "brain unavailable"}
        return {"success": True, "text": output.strip(), "error": None}

    def rewrite(self, text: str, instruction: str) -> Dict:
        """Rewrites `text` per `instruction` (e.g. "make it shorter",
        "make it more formal", "fix the grammar"). Returns
        {"success": bool, "text": str, "error": Optional[str]}."""
        if not text or not instruction:
            return {"success": False, "text": "", "error": "text and instruction both required"}
        system_prompt = (
            f"Rewrite the given text following this instruction: " f"{instruction}. Reply with the rewritten text only."
        )
        output = self._call_brain(system_prompt, text)
        if output is None:
            return {"success": False, "text": "", "error": "brain unavailable"}
        return {"success": True, "text": output.strip(), "error": None}

    @staticmethod
    def _call_brain(system_prompt: str, user_prompt: str) -> Optional[str]:
        """See coder.py's _call_brain() docstring - identical
        contract, calling the same ai/cloud_models/groq_client.py
        chat_with_tools() with no tools bound."""
        try:
            from ai.cloud_models.groq_client import get_ultron_client as get_groq_client
        except Exception:
            return None
        try:
            client = get_groq_client()
            messages: List[Dict] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = client.chat_with_tools(messages=messages, tools=[])
            if isinstance(response, dict):
                return response.get("content") or response.get("text")
            return str(response) if response else None
        except Exception:
            return None


_writer: Optional[WriterAgent] = None


def get_writer() -> WriterAgent:
    global _writer
    if _writer is None:
        _writer = WriterAgent()
    return _writer
