"""
Teacher Agent
=============
Explains a concept at a chosen level and can generate a short quiz to
check understanding of it. Distinct from writer.py: writer.py's output
is the finished artifact itself (an email, a post); this agent's
output is scaffolding meant to build understanding, so it always
takes a target `level` and leans toward breaking things into steps
rather than producing polished, ready-to-send prose. Distinct from
coder.py's explain(): coder.py explains code that already exists,
this agent explains a topic from scratch and can go on to quiz the
learner about it.
"""

from typing import Dict, List, Optional


class TeacherAgent:
    """LLM-backed concept explanation and quizzing. Use get_teacher()."""

    def is_available(self) -> bool:
        return self._call_brain("ping", "ping") is not None

    def explain(self, topic: str, level: str = "beginner") -> Dict:
        """Explains `topic` for a `level` learner ("beginner",
        "intermediate", "advanced" - a hint, not a strict rubric).
        Returns
        {"success": bool, "explanation": str, "error": Optional[str]}."""
        if not topic:
            return {"success": False, "explanation": "", "error": "no topic given"}
        system_prompt = (
            f"Explain the given topic to a {level} learner. Break it "
            f"into clear steps or sub-points rather than one dense "
            f"paragraph. Use an analogy if it genuinely helps, skip it "
            f"if it wouldn't."
        )
        output = self._call_brain(system_prompt, topic)
        if output is None:
            return {"success": False, "explanation": "", "error": "brain unavailable"}
        return {"success": True, "explanation": output.strip(), "error": None}

    def quiz(self, topic: str, num_questions: int = 3) -> Dict:
        """Generates `num_questions` short comprehension questions
        about `topic`, one per line, no answers included (so it's
        actually usable as a quiz rather than an answer key). Returns
        {"success": bool, "questions": List[str], "error": Optional[str]}."""
        if not topic:
            return {"success": False, "questions": [], "error": "no topic given"}
        count = max(1, num_questions)
        system_prompt = (
            f"Write exactly {count} short comprehension questions "
            f"about the given topic, one per line, numbered. Do not "
            f"include answers."
        )
        output = self._call_brain(system_prompt, topic)
        if output is None:
            return {"success": False, "questions": [], "error": "brain unavailable"}
        questions = [line.strip() for line in output.strip().splitlines() if line.strip()]
        return {"success": True, "questions": questions, "error": None}

    @staticmethod
    def _call_brain(system_prompt: str, user_prompt: str) -> Optional[str]:
        """See coder.py's _call_brain() docstring - identical
        contract."""
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


_teacher: Optional[TeacherAgent] = None


def get_teacher() -> TeacherAgent:
    global _teacher
    if _teacher is None:
        _teacher = TeacherAgent()
    return _teacher
