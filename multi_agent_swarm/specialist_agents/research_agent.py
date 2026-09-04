"""
Swarm research agent
======================
Specialist wrapper around skills/web/research.py's WebResearch
(unchanged - multi-query search, top-page reads, cited synthesis).
WebResearch takes its ai_router as a constructor-injected dependency
rather than importing ai/ai_router.py at module load time (same
circular-import concern that module's own docstring calls out), so
this wrapper does the lazy import here instead, once, on first use.
"""

from typing import Dict

from skills.web.research import WebResearch
from multi_agent_swarm.specialist_agents.base_specialist import BaseSpecialistAgent


class SwarmResearchAgent(BaseSpecialistAgent):
    """Multi-source web research with a cited, synthesized answer."""

    capabilities = ["research", "web", "search", "information"]
    keywords = [
        "research",
        "search",
        "find information",
        "look up",
        "investigate",
        "sources",
        "learn about",
        "what is",
        "who is",
        "latest news",
    ]

    def __init__(self):
        super().__init__("research", "Multi-source web research with cited synthesis")
        self._backend = None  # built lazily - needs the AI router

    def _get_backend(self) -> WebResearch:
        if self._backend is None:
            from ai.ai_router import AIRouter

            self._backend = WebResearch(ai_router=AIRouter())
        return self._backend

    def _run(self, task: Dict) -> Dict:
        query = task.get("description") or task.get("query")
        if not query:
            return {"error": "No query/description provided for a research task"}
        return self._get_backend().research(
            query,
            num_queries=task.get("num_queries", 3),
            results_per_query=task.get("results_per_query", 3),
        )
