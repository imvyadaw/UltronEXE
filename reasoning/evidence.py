"""
Evidence (Phase 30 - Reasoning)
==================================
ai/rag_engine.py already retrieves relevant chunks from Ultron's own
indexed knowledge for a query - but it returns them as an answer, not
as a labeled, re-usable evidence set another module can attach to a
specific claim and reason about. This module is that thin wrapper:
gather_for_claim() pulls candidate support from RAGEngine (and, best-
effort, memory/semantic_memory.py if available) and returns a
normalized Evidence list that reasoning/fact_checker.py scores
against - kept separate from RAGEngine itself so fact_checker.py
doesn't need to know where evidence came from, only that it has a
source, a snippet, and a rough relevance score.
"""

from dataclasses import dataclass
from typing import List

from core.logger import get_logger

logger = get_logger("ultron.reasoning.evidence")


@dataclass
class Evidence:
    source: str
    snippet: str
    relevance: float = 0.0


def gather_for_claim(claim: str, top_k: int = 5) -> List[Evidence]:
    """Best-effort - each source is wrapped individually so one
    unavailable backend (e.g. no vector DB configured) doesn't block
    the others from contributing."""
    results: List[Evidence] = []

    try:
        from ai.rag_engine import RAGEngine

        rag_result = RAGEngine().retrieve(claim, top_k=top_k)
        for chunk in rag_result.get("chunks", []) or []:
            results.append(
                Evidence(
                    source=chunk.get("source", "rag_engine"),
                    snippet=chunk.get("text", "")[:500],
                    relevance=chunk.get("score", 0.5),
                )
            )
    except Exception as e:
        logger.debug(f"RAG evidence gathering skipped: {e}")

    try:
        from memory.semantic_memory import get_semantic_memory

        hits = get_semantic_memory().search(claim, top_k=top_k)
        for hit in hits or []:
            results.append(
                Evidence(
                    source="semantic_memory",
                    snippet=str(hit.get("content", hit))[:500],
                    relevance=hit.get("score", 0.4) if isinstance(hit, dict) else 0.4,
                )
            )
    except Exception as e:
        logger.debug(f"Semantic memory evidence gathering skipped: {e}")

    results.sort(key=lambda e: e.relevance, reverse=True)
    return results[:top_k]
