"""Source validator
=================
Scores how much a source of information should be trusted, before
learning/knowledge_extractor.py lets anything it says into the
knowledge base. Two layers:

1. Domain heuristics - cheap, always available, no network/LLM call:
   well-known reference/government/academic/wire-service domains score
   high, known low-quality patterns (content-farm blog hosts, forum
   threads, no domain at all) score low, everything else sits at a
   neutral default.
2. Persisted verdicts - knowledge_base/sources/ remembers any source
   Ultron has already scored, or that the user has explicitly overridden
   via set_manual_trust() (e.g. "always trust my own notes", "never
   trust this site again"), so the same domain isn't re-judged by
   heuristics every time.

This is a trust *tier* for "how much should one uncorroborated claim
from here move the needle" - it never calls out to a fact-checking API
and is not a truth-checker. Corroboration across independent sources
(learning/confidence.py) is what actually raises confidence over time.
"""

from typing import Dict, Optional
from urllib.parse import urlparse

from knowledge_base import KnowledgeBase

# Specific domains known to be generally reliable references.
TRUSTED_DOMAINS = {
    "wikipedia.org",
    "britannica.com",
    "nature.com",
    "sciencedirect.com",
    "ncbi.nlm.nih.gov",
    "who.int",
    "un.org",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "pib.gov.in",
}
# Any domain ending in one of these suffixes is treated as trusted
# (government / academic institutions).
TRUSTED_SUFFIXES = (".gov", ".edu", ".gov.in", ".nic.in", ".ac.uk", ".ac.in")
# Substrings that mark user-generated / low-editorial-control content.
LOW_QUALITY_PATTERNS = (
    "blogspot.",
    "wordpress.com",
    "medium.com/@",
    "pastebin.com",
    "reddit.com/r/",
    "quora.com",
    "answers.yahoo.com",
)

TIER_SCORES = {"trusted": 0.9, "neutral": 0.5, "low_quality": 0.2, "unverified": 0.35}


class SourceValidator:
    """Assigns a trust_score (0-1) and tier to a source, and persists the
    verdict in the knowledge base so it's reusable across extractions."""

    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self.kb = kb or KnowledgeBase()

    def validate(self, name: str, url: Optional[str] = None) -> Dict:
        """Look up (or compute + persist) a trust verdict for a source.
        Returns the stored knowledge_base/sources/ record."""
        try:
            existing = self.kb.sources.find(url=url) or self.kb.sources.find(name=name)
            if existing:
                return existing[0]
            tier = self._heuristic_tier(url) if url else "unverified"
            return self.kb.add_source(name=name, url=url, trust_score=TIER_SCORES[tier], tier=tier)
        except Exception as e:
            return {"error": str(e)}

    def set_manual_trust(self, source_id: str, trust_score: float, reason: str = "") -> Dict:
        """Explicit user override of a source's trust score."""
        trust_score = _clamp(trust_score)
        if trust_score >= 0.75:
            tier = "trusted"
        elif trust_score <= 0.3:
            tier = "low_quality"
        else:
            tier = "neutral"
        return self.kb.sources.update(source_id, trust_score=trust_score, tier=tier, manual_override_reason=reason)

    def trust_score_for(self, source_id: str) -> float:
        """Convenience lookup used by confidence scoring / re-validation."""
        record = self.kb.sources.get(source_id)
        return record.get("trust_score", TIER_SCORES["unverified"]) if record else TIER_SCORES["unverified"]

    # -- heuristics ----------------------------------------------------
    def _domain(self, url: str) -> str:
        try:
            netloc = urlparse(url if "://" in url else f"//{url}").netloc.lower()
            return netloc[4:] if netloc.startswith("www.") else netloc
        except Exception:
            return url.lower()

    def _heuristic_tier(self, url: str) -> str:
        domain = self._domain(url)
        if not domain:
            return "unverified"
        lowered = url.lower()
        if any(pattern in lowered for pattern in LOW_QUALITY_PATTERNS):
            return "low_quality"
        if domain in TRUSTED_DOMAINS or any(domain.endswith(f".{d}") for d in TRUSTED_DOMAINS):
            return "trusted"
        if domain.endswith(TRUSTED_SUFFIXES):
            return "trusted"
        return "neutral"


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))
