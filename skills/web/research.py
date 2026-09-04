"""
Web research skill
====================
Multi-source research: runs several search queries, reads the top pages of
each, and hands the collected text to Ultron's own AI router to produce a
cited summary. Builds on skills/internet/web_tools.py (search + read) and
ai/ai_router.py (whichever LLM backend - Groq/local - is currently active).

Speed note: the search queries and the page reads were previously each run
one-at-a-time in a for-loop, so a 3-query/3-page research pass paid for
6 sequential network round trips back to back (worst case 60s+ at the old
10s timeouts). Both loops now run concurrently via a thread pool - since
these are blocking I/O calls (requests), threads overlap the wait time
instead of adding it up, which is the actual fix for "google se info lena
bahut slow hai".
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from skills.internet.web_tools import WebTools


class WebResearch:
    """Runs multi-query research and (optionally) summarizes with the AI router."""

    def __init__(self, ai_router=None):
        self.web = WebTools()
        # ai_router is injected rather than imported at module load time to
        # avoid a circular import (ai_router itself may end up depending on
        # tool_runtime, which depends on skills/*). Pass an object exposing
        # a `.chat(prompt) -> str` method, e.g. ai.ai_router.AIRouter().
        self.ai_router = ai_router

    def gather_sources(self, query: str, num_queries: int = 3, results_per_query: int = 3, read_top_n: int = 3) -> Dict:
        """Run the query plus AI-free simple variants, dedupe URLs, and read
        the top N pages' full text for downstream summarization."""
        try:
            variants = [query]
            if num_queries > 1:
                variants.append(f"{query} explained")
            if num_queries > 2:
                variants.append(f"{query} latest")

            queries = variants[:num_queries]
            with ThreadPoolExecutor(max_workers=max(1, len(queries))) as pool:
                search_results = list(
                    pool.map(
                        lambda q: self.web.search_internet(q, num_results=results_per_query),
                        queries,
                    )
                )

            seen_urls = set()
            all_results = []
            for res in search_results:
                if res.get("success"):
                    for r in res["results"]:
                        if r["url"] not in seen_urls:
                            seen_urls.add(r["url"])
                            all_results.append(r)

            top_results = all_results[:read_top_n]
            sources = []
            if top_results:
                with ThreadPoolExecutor(max_workers=max(1, len(top_results))) as pool:
                    pages = list(pool.map(lambda r: self.web.read_url(r["url"]), top_results))
                for r, page in zip(top_results, pages):
                    sources.append(
                        {
                            "title": r.get("title", ""),
                            "url": r["url"],
                            "description": r.get("description", ""),
                            "content": page.get("content", "") if page.get("success") else "",
                        }
                    )

            return {
                "success": True,
                "query": query,
                "result_count": len(all_results),
                "sources_read": len(sources),
                "results": all_results,
                "sources": sources,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def research(self, query: str, num_queries: int = 3, results_per_query: int = 3) -> Dict:
        """Full pipeline: gather sources, then (if an ai_router was provided)
        ask the LLM to synthesize a cited answer. Without an ai_router, returns
        the raw gathered sources so the caller's own LLM turn can summarize them."""
        gathered = self.gather_sources(query, num_queries=num_queries, results_per_query=results_per_query)
        if not gathered["success"]:
            return gathered

        if self.ai_router is None:
            gathered["note"] = "No ai_router supplied - returning raw sources for the caller to summarize."
            return gathered

        try:
            context = "\n\n".join(
                f"[Source {i+1}: {s['title']} - {s['url']}]\n{s['content'][:2000]}"
                for i, s in enumerate(gathered["sources"])
                if s["content"]
            )
            prompt = (
                f"Research question: {query}\n\n"
                f"Sources:\n{context}\n\n"
                "Write a concise, well-organized answer based only on the sources above. "
                "Cite sources inline as [Source N]."
            )
            summary = self.ai_router.chat(prompt)
            gathered["summary"] = summary
            return gathered
        except Exception as e:
            gathered["summary_error"] = str(e)
            return gathered
