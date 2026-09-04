"""
Web agent
=========
Thin wrapper over skills/internet (search + weather) and skills/browser
so callers that want direct web access (without going through the LLM
tool-calling loop) have one place to reach for it - mirrors the shape
of agents/memory_agent.py.
"""

from typing import Dict, List

from skills.internet.web_tools import WebTools
from skills.internet.weather import WeatherLookup
from agents.base_agent import BaseAgent


class WebAgent(BaseAgent):
    """Search, read pages, and check weather."""

    capabilities = ["web", "search", "weather", "research"]

    def __init__(self):
        super().__init__("web", "Web search, page reading, and weather lookups")
        self.web = WebTools()
        self.weather = WeatherLookup()

    def search(self, query: str, num_results: int = 5) -> Dict:
        """Search the internet for `query`."""
        return self.web.search_internet(query, num_results)

    def read_url(self, url: str) -> Dict:
        """Fetch and read the main text content of a specific web page."""
        if hasattr(self.web, "read_url"):
            return self.web.read_url(url)
        return {"error": "read_url not available on WebTools"}

    def get_weather(self, location: str = "") -> Dict:
        """Current weather for `location` (blank = auto-detect by IP)."""
        return self.weather.get_weather(location)

    def research(self, topic: str, num_results: int = 5) -> Dict:
        """Search a topic, then fetch the readable text of each result -
        a small "deep search" helper for questions that need more than
        a snippet to answer well."""
        search_result = self.search(topic, num_results)
        results = search_result.get("results", [])
        pages: List[Dict] = []
        for r in results:
            url = r.get("url")
            if not url:
                continue
            page = self.read_url(url)
            pages.append({"url": url, "title": r.get("title", ""), "content": page})
        return {"topic": topic, "sources_checked": len(pages), "pages": pages}

    def monitor_url(self, url: str, keyword: str) -> Dict:
        """Fetch a page and report whether `keyword` currently appears on it -
        useful for a one-shot "has this page changed to mention X" check."""
        page = self.read_url(url)
        if "error" in page:
            return page
        text = str(page.get("content", page)).lower()
        found = keyword.lower() in text
        return {"url": url, "keyword": keyword, "found": found}
