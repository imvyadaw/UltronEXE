"""
Evidence Ledger Manager (P2 - Evidence Ledger & Confidence Tracking)
=====================================================================
Entry point for the evidence_ledger/ package. Sits directly downstream
of reasoning/fact_checker.py: every FactCheckResult it produces gets
logged here (see ai/phase30_extended_tools.py's _check_fact, which now
calls log_fact_check_result() best-effort after every check_fact tool
call), and later, when the real outcome is known, record_outcome()
feeds that back into per-source reliability.

Usage:
    from intelligence.evidence_ledger import get_evidence_ledger
    ledger = get_evidence_ledger()

    entry = ledger.log_claim("The meeting is at 3pm", "supported", 0.82,
                              evidence=[{"source": "google_calendar", "snippet": "...", "relevance": 0.9}])
    ...later, once the user says "actually it moved to 4"...
    ledger.record_outcome(entry["id"], "confirmed_false", note="user corrected: moved to 4pm")

    ledger.why_did_you_believe("meeting is at 3pm")  # -> most recent matching entry
    ledger.get_source_reliability("google_calendar")  # -> {"reliability_score": ...}
"""

from typing import Dict, List, Optional

from intelligence.evidence_ledger.ledger_store import get_evidence_ledger_store


class EvidenceLedger:
    def __init__(self):
        self._store = get_evidence_ledger_store()

    def log_claim(
        self, claim: str, verdict: str, confidence: float, evidence: Optional[List[Dict]] = None, context: str = ""
    ) -> Dict:
        return self._store.log_entry(claim, verdict, confidence, evidence, context)

    def log_fact_check_result(self, result, context: str = "") -> Dict:
        """Convenience wrapper for a reasoning.fact_checker.FactCheckResult
        (or any object with .claim/.verdict/.confidence/.evidence attrs) -
        avoids every caller needing to know the ledger's raw dict shape."""
        evidence = [
            {"source": e.source, "snippet": e.snippet, "relevance": e.relevance}
            for e in getattr(result, "evidence", [])
        ]
        return self.log_claim(result.claim, result.verdict, result.confidence, evidence, context)

    def record_outcome(self, entry_id: str, outcome: str, note: str = "") -> bool:
        return self._store.record_outcome(entry_id, outcome, note)

    def why_did_you_believe(self, claim_substring: str) -> Optional[Dict]:
        """Answers 'why did you say/believe X' - most recent ledger entry
        whose claim text matches, with its full evidence trail. Returns
        None (not an error) when nothing matches - callers should treat
        that as 'no record of this', which is itself a useful answer."""
        matches = self._store.find_by_claim(claim_substring, limit=1)
        return matches[0] if matches else None

    def get_recent_entries(self, limit: int = 20) -> List[Dict]:
        return self._store.get_recent(limit)

    def get_source_reliability(self, source: str) -> Dict:
        return self._store.get_source_stats(source)

    def get_all_source_reliability(self) -> List[Dict]:
        return self._store.get_all_source_stats()

    def get_untrustworthy_sources(self, min_citations: int = 3, threshold: float = 0.4) -> List[Dict]:
        """Sources with enough judged history to be meaningful whose
        reliability has dropped below threshold - worth surfacing so a
        source that's quietly gone bad doesn't keep getting cited."""
        return [
            s
            for s in self._store.get_all_source_stats()
            if (s["times_correct"] + s["times_wrong"]) >= min_citations and s["reliability_score"] < threshold
        ]


_instance: Optional[EvidenceLedger] = None


def get_evidence_ledger() -> EvidenceLedger:
    global _instance
    if _instance is None:
        _instance = EvidenceLedger()
    return _instance
