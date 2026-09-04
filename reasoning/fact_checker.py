"""
Fact Checker (Phase 30 - Reasoning)
======================================
intelligence/reasoning_engine.py decides *how hard to think* about a
request; nothing decides whether the specific factual claims that
thinking produces are actually well-supported before
core/orchestrator.py acts on them or states them out loud. This
module is that check: given a claim, gather supporting
reasoning/evidence.py, and return a confidence-labeled verdict so the
orchestrator can decide to proceed, ask the user to confirm, or
re-query before treating the claim as ground truth for a plan.

Deliberately conservative in the absence of evidence - no evidence
found is UNVERIFIED, not "assumed true".
"""

from dataclasses import dataclass
from typing import List, Optional

from core.logger import get_logger
from reasoning.evidence import Evidence, gather_for_claim

logger = get_logger("ultron.reasoning.fact_checker")

CONFIDENT_THRESHOLD = 0.7
WEAK_THRESHOLD = 0.35


@dataclass
class FactCheckResult:
    claim: str
    verdict: str  # "supported" | "weakly_supported" | "unverified" | "contradicted"
    confidence: float
    evidence: List[Evidence]


class FactChecker:
    def check(self, claim: str, top_k: int = 5) -> FactCheckResult:
        evidence = gather_for_claim(claim, top_k=top_k)

        if not evidence:
            return FactCheckResult(claim, "unverified", 0.0, [])

        top_relevance = evidence[0].relevance
        avg_relevance = sum(e.relevance for e in evidence) / len(evidence)
        confidence = round((top_relevance * 0.6) + (avg_relevance * 0.4), 3)

        if confidence >= CONFIDENT_THRESHOLD:
            verdict = "supported"
        elif confidence >= WEAK_THRESHOLD:
            verdict = "weakly_supported"
        else:
            verdict = "unverified"

        logger.info(f"Fact check '{claim[:60]}...' -> {verdict} (confidence={confidence})")
        return FactCheckResult(claim, verdict, confidence, evidence)

    def should_proceed_without_confirmation(self, result: FactCheckResult) -> bool:
        return result.verdict == "supported"


_instance: Optional[FactChecker] = None


def get_fact_checker() -> FactChecker:
    global _instance
    if _instance is None:
        _instance = FactChecker()
    return _instance
