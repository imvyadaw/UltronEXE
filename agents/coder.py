"""
Coder Agent
===========
Writes, reviews, and explains code on request - it does not run any of
it. Execution stays where this project already put it:
PHASE_17_2_COGNITIVE_BRAIN/COGNITIVE_CORE/autonomous_executor.py for a
multi-step goal loop, core/executor.py for a single dispatched action.
Keeping "produce code" and "run code" as separate modules, with
guard.py's review_code() sitting between them, means a caller has to
deliberately choose to execute what this agent hands back rather than
that happening as a side effect of asking for code.

Same optional-dependency contract as PHASE_18_5_SEARCH_ENGINE: no
`ai.cloud_models.groq_client` module, no configured model, or any
call failure all collapse to {"success": False, ...} rather than an
exception. The groq_client import is lazy (inside methods), same
reasoning as SEARCH/people_search.py importing google_search lazily -
this module works standalone if the brain isn't wired up yet.
"""

from typing import Dict, Optional


class CoderAgent:
    """LLM-backed code generation/review/explanation. Use get_coder()."""

    def is_available(self) -> bool:
        return self._call_brain("ping", "ping") is not None

    def generate(self, task: str, language: str = "python") -> Dict:
        """Writes code for `task` in `language`. Returns
        {"success": bool, "code": str, "error": Optional[str]}.
        Does not run guard.py itself - callers that will execute the
        result should call guard.get_guard().review_code() on `code`
        first."""
        if not task:
            return {"success": False, "code": "", "error": "no task given"}
        system_prompt = (
            f"You are a precise {language} coding assistant. Reply with "
            f"working {language} code only, no prose before or after, "
            f"no markdown code fences."
        )
        output = self._call_brain(system_prompt, task)
        if output is None:
            return {"success": False, "code": "", "error": "brain unavailable"}
        return {"success": True, "code": output.strip(), "error": None}

    def review(self, code: str, language: str = "python") -> Dict:
        """Reviews `code` for bugs, edge cases, and readability -
        style/correctness feedback only, not a safety audit; that's
        guard.py's job. Returns
        {"success": bool, "notes": str, "error": Optional[str]}."""
        if not code:
            return {"success": False, "notes": "", "error": "no code given"}
        system_prompt = (
            f"You are a {language} code reviewer. List concrete bugs, "
            f"edge cases, and readability issues in the given code as "
            f"short bullet points. If the code looks correct, say so "
            f"plainly instead of inventing issues."
        )
        output = self._call_brain(system_prompt, code)
        if output is None:
            return {"success": False, "notes": "", "error": "brain unavailable"}
        return {"success": True, "notes": output.strip(), "error": None}

    def explain(self, code: str) -> Dict:
        """Plain-language walkthrough of what `code` does. Returns
        {"success": bool, "explanation": str, "error": Optional[str]}."""
        if not code:
            return {"success": False, "explanation": "", "error": "no code given"}
        system_prompt = (
            "Explain what the given code does in plain language, "
            "step by step, for someone reading it for the first time."
        )
        output = self._call_brain(system_prompt, code)
        if output is None:
            return {"success": False, "explanation": "", "error": "brain unavailable"}
        return {"success": True, "explanation": output.strip(), "error": None}

    @staticmethod
    def _call_brain(system_prompt: str, user_prompt: str) -> Optional[str]:
        """Lazily calls this project's existing Groq client
        (ai/cloud_models/groq_client.py's UltronGroqClient.chat_with_tools()).
        Returns None on any missing module, missing client, or call
        failure so every public method above can fall back cleanly.

        Fixed: this used to call chat_with_tools(messages=messages,
        tools=[]), but that method's real signature is
        chat_with_tools(user_message: str, tool_callback=None) -> str -
        it builds its own message history internally via
        _build_messages() and returns a plain string, not a dict. The
        messages=/tools= kwargs don't exist on it, so every call here
        raised TypeError, which the try/except below swallowed - meaning
        CoderAgent silently reported itself as permanently unavailable
        no matter what. There's no separate system-prompt parameter on
        the real method, so system_prompt is folded into the single
        user_message string instead."""
        try:
            from ai.cloud_models.groq_client import get_ultron_client as get_groq_client
        except Exception:
            return None
        try:
            client = get_groq_client()
            combined = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
            response = client.chat_with_tools(combined)
            return response if isinstance(response, str) and response.strip() else None
        except Exception:
            return None


_coder: Optional[CoderAgent] = None


def get_coder() -> CoderAgent:
    global _coder
    if _coder is None:
        _coder = CoderAgent()
    return _coder
