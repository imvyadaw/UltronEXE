"""
Reasoning
=========
Lightweight chain-of-thought pass over a request before handing it to
ai.planning / core.executor - useful for questions that need Ultron to
think through a few sub-points before acting or answering, without
the overhead of a full multi-tool plan.

Goes through ai.ai_router (like every other AI request in Ultron) instead
of holding its own Groq connection, so this also gets automatic
online/offline fallback for free instead of hard-failing when there's no
GROQ_API_KEY or no internet.
"""

from typing import Dict

from ai.ai_router import get_router

REASONING_PROMPT = """Think step by step about the following, in 3-5 short numbered points,
then give a one-line final conclusion prefixed with "Conclusion:".
Be concise - this is internal reasoning, not a full essay.

Request: {goal}"""


class ReasoningEngine:
    """Runs a short chain-of-thought pass over a goal/question."""

    def reason(self, goal: str) -> Dict:
        """Produce a short chain-of-thought + conclusion for `goal`."""
        try:
            text = get_router().complete(REASONING_PROMPT.format(goal=goal), temperature=0.4, max_tokens=400)

            conclusion = ""
            if "Conclusion:" in text:
                conclusion = text.split("Conclusion:", 1)[1].strip()

            return {"goal": goal, "reasoning": text, "conclusion": conclusion}
        except Exception as e:
            return {"error": str(e)}
