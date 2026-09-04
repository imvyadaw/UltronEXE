"""
Researcher Agent
================
Builds on search the same way
people_search.py builds on google_search.py: this module makes no
HTTP calls of its own. research() gathers results from
get_google_search() and get_news_search(), then hands only those
actual results to the brain to summarize - the summary is grounded in
what search really returned, never the model filling gaps from its
own training data, same "flag, don't invent" posture fact_check.py's
docstring already commits to for this phase.

verify_claim() goes one step further than research(): it calls
get_fact_check() specifically and, when publishers have already rated
the claim, has the brain restate their ratings with attribution - it
never asks the brain for its own true/false verdict, matching
fact_check.py's own promise not to invent one.

Cross-phase import of search is done lazily
inside methods, same as every cross-module import elsewhere in this
project - this file works (returning "brain unavailable" or empty
sources) even if Phase 18.5 isn't on the path.
"""

from typing import Dict, List, Optional


class ResearcherAgent:
    """Multi-source research + grounded summarization. Use get_researcher()."""

    def is_available(self) -> bool:
        return self._call_brain("ping", "ping") is not None

    def research(self, topic: str, num_sources: int = 5) -> Dict:
        """Pulls up to `num_sources` results each from google_search
        and news_search for `topic`, then asks the brain for a short
        summary citing only those results. Returns
        {"success": bool, "summary": str, "sources": List[Dict],
        "error": Optional[str]}. `sources` is populated even if the
        summarization step fails, so a caller always gets the raw
        material back."""
        if not topic:
            return {"success": False, "summary": "", "sources": [], "error": "no topic given"}

        sources = self._gather_sources(topic, num_sources)
        if not sources:
            return {
                "success": False,
                "summary": "",
                "sources": [],
                "error": "no search results available",
            }

        source_block = "\n".join(
            f"- {s.get('title', '')} ({s.get('url', '')}): {s.get('snippet', '')}" for s in sources
        )
        system_prompt = (
            "Summarize the topic using only the facts present in the "
            "sources below. Do not add anything not supported by "
            "them. If the sources disagree, say so instead of picking "
            "a side."
        )
        user_prompt = f"Topic: {topic}\n\nSources:\n{source_block}"
        output = self._call_brain(system_prompt, user_prompt)
        if output is None:
            return {
                "success": False,
                "summary": "",
                "sources": sources,
                "error": "brain unavailable",
            }
        return {"success": True, "summary": output.strip(), "sources": sources, "error": None}

    def verify_claim(self, claim: str) -> Dict:
        """Looks `claim` up via fact_check.py and, if any published
        ratings exist, has the brain restate them with attribution -
        never its own verdict. Returns
        {"success": bool, "summary": str, "ratings": List[Dict],
        "error": Optional[str]}. An empty `ratings` list with
        success=True means no publisher has covered this claim, which
        is itself a real (if unhelpful) answer - not an error."""
        if not claim:
            return {"success": False, "summary": "", "ratings": [], "error": "no claim given"}
        try:
            from search.fact_check import get_fact_check

            ratings = get_fact_check().check_claim(claim)
        except Exception:
            ratings = []

        if not ratings:
            return {
                "success": True,
                "summary": "No fact-checking publisher has covered this claim.",
                "ratings": [],
                "error": None,
            }

        ratings_block = "\n".join(
            f"- {r.get('publisher', 'unknown publisher')} rated a similar claim "
            f"\"{r.get('claim_text', '')}\" as: {r.get('rating', 'unrated')}"
            for r in ratings
        )
        system_prompt = (
            "Restate the following published fact-check ratings in "
            "plain language, with attribution to each publisher. Do "
            "not add your own judgment of whether the claim is true."
        )
        output = self._call_brain(system_prompt, ratings_block)
        summary = output.strip() if output else ratings_block
        return {"success": True, "summary": summary, "ratings": ratings, "error": None}

    @staticmethod
    def _gather_sources(topic: str, num_sources: int) -> List[Dict]:
        sources: List[Dict] = []
        try:
            from search.google_search import get_google_search

            sources.extend(get_google_search().search(topic, num=num_sources))
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("agents.researcher._gather_sources")
        try:
            from search.news_search import get_news_search

            sources.extend(get_news_search().search(topic, num=num_sources))
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("agents.researcher._gather_sources")
        return sources

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


_researcher: Optional[ResearcherAgent] = None


def get_researcher() -> ResearcherAgent:
    global _researcher
    if _researcher is None:
        _researcher = ResearcherAgent()
    return _researcher
