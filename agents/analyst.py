"""
Analyst Agent
=============
Analyzes text or numbers the caller already has in hand - it doesn't
open files, query databases, or fetch anything itself. That scope cut
is deliberate: pulling data in is a different concern from making
sense of it, and this project already has dedicated modules for the
former in earlier phases (file/browser automation). analyze_numbers()
computes its descriptive stats with plain arithmetic, not the brain -
mean/median/min/max/trend are exact, deterministic answers, and asking
an LLM for them would trade a correct answer for a plausible-sounding
one. The brain only gets involved for analyze_numbers()'s optional
plain-language interpretation, and even then it's handed the already-
computed stats rather than the raw numbers, so it's explaining real
figures instead of re-deriving them.
"""

from typing import Dict, List, Optional


class AnalystAgent:
    """Text/numeric analysis. Use get_analyst()."""

    def is_available(self) -> bool:
        return self._call_brain("ping", "ping") is not None

    def analyze_text(self, text: str, question: Optional[str] = None) -> Dict:
        """Summarizes `text`, or answers `question` about it if
        given. Returns
        {"success": bool, "result": str, "error": Optional[str]}."""
        if not text:
            return {"success": False, "result": "", "error": "no text given"}
        if question:
            system_prompt = (
                "Answer the question using only information present "
                "in the given text. If the text doesn't contain the "
                "answer, say so instead of guessing."
            )
            user_prompt = f"Text:\n{text}\n\nQuestion: {question}"
        else:
            system_prompt = "Summarize the key points of the given text concisely."
            user_prompt = text
        output = self._call_brain(system_prompt, user_prompt)
        if output is None:
            return {"success": False, "result": "", "error": "brain unavailable"}
        return {"success": True, "result": output.strip(), "error": None}

    def analyze_numbers(self, data: List[float], interpret: bool = True) -> Dict:
        """Computes count/min/max/mean/median/trend over `data`
        directly (no brain call for the numbers themselves - see
        module docstring). When `interpret` is True and the brain is
        available, adds a plain-language `interpretation` of those
        exact stats; when it isn't, `interpretation` is None but
        `stats` is still returned in full. Returns
        {"success": bool, "stats": Dict, "interpretation": Optional[str],
        "error": Optional[str]}."""
        if not data:
            return {"success": False, "stats": {}, "interpretation": None, "error": "no data given"}
        try:
            numbers = [float(x) for x in data]
        except (TypeError, ValueError):
            return {"success": False, "stats": {}, "interpretation": None, "error": "data must be numeric"}

        sorted_numbers = sorted(numbers)
        count = len(sorted_numbers)
        mid = count // 2
        median = sorted_numbers[mid] if count % 2 == 1 else (sorted_numbers[mid - 1] + sorted_numbers[mid]) / 2
        stats = {
            "count": count,
            "min": sorted_numbers[0],
            "max": sorted_numbers[-1],
            "mean": sum(sorted_numbers) / count,
            "median": median,
            "trend": "up" if numbers[-1] > numbers[0] else ("down" if numbers[-1] < numbers[0] else "flat"),
        }

        interpretation = None
        if interpret:
            system_prompt = (
                "Given these already-computed statistics, write one or "
                "two plain-language sentences describing what they "
                "show. Do not recompute or second-guess the numbers."
            )
            interpretation = self._call_brain(system_prompt, str(stats))

        return {"success": True, "stats": stats, "interpretation": interpretation, "error": None}

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


_analyst: Optional[AnalystAgent] = None


def get_analyst() -> AnalystAgent:
    global _analyst
    if _analyst is None:
        _analyst = AnalystAgent()
    return _analyst
