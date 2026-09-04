"""
Swarm writer agent
====================
Genuinely new capability (nothing in agents/ or skills/ already does
this) - a focused content-writing specialist for the swarm, structured
the same way agents/coding_agent.py is: no tool-calling loop, no chat
history, just a tight system prompt per task and a direct Groq call,
because drafting wants a clean context the same way code generation
does rather than the assistant's conversational history bleeding in.
"""

from typing import Dict

from groq import Groq

from config import GROQ_API_KEY, MODEL_NAME
from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent

_WRITER_SYSTEM_PROMPT = (
    "You are a skilled writing assistant. Produce clear, well-organized "
    "prose in the tone and format requested. Output only the requested "
    "content - no meta-commentary about what you're about to write, no "
    "disclaimers, unless explicitly asked to explain your choices."
)

#: task["action"] -> instruction template. {description} is the task's
#: description/content; {tone} defaults to "clear and professional".
_ACTIONS = {
    "draft": "Write {tone} content on the following:\n\n{description}",
    "summarize": "Summarize the following {tone}, in {length} or less:\n\n{description}",
    "rewrite": "Rewrite the following to be {tone}:\n\n{description}",
    "outline": "Produce a structured outline (headings + bullets) for:\n\n{description}",
}


class SwarmWriterAgent(BaseSpecialistAgent):
    """Draft, summarize, rewrite, or outline text, dispatched from the swarm."""

    capabilities = ["writing", "content", "draft", "summarize", "copy"]
    keywords = [
        "write",
        "draft",
        "blog",
        "article",
        "email",
        "summary",
        "summarize",
        "content",
        "copy",
        "essay",
        "outline",
        "rewrite",
        "proofread",
    ]

    def __init__(self):
        super().__init__("writer", "Drafts, summarizes, rewrites, and outlines text")
        self._client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

    def _ask(self, user_prompt: str) -> Dict:
        if not self._client:
            return {"error": "GROQ_API_KEY not set - see config.py's diagnose_env()"}
        try:
            response = self._client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": _WRITER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.6,
            )
            return {"result": response.choices[0].message.content}
        except Exception as e:
            return {"error": str(e)}

    def _run(self, task: Dict) -> Dict:
        description = task.get("description") or task.get("content")
        if not description:
            return {"error": "No description/content provided for a writing task"}

        action = (task.get("action") or "draft").lower()
        template = _ACTIONS.get(action)
        if template is None:
            return {"error": f"Unknown writer action '{action}' - use one of {list(_ACTIONS)}"}

        prompt = template.format(
            description=description,
            tone=task.get("tone", "clear and professional"),
            length=task.get("length", "150 words"),
        )
        return self._ask(prompt)
