"""
Evidence Ledger (P2 - Evidence Ledger & Confidence Tracking)
=============================================================
Persistent record of every claim Ultron has fact-checked, what
evidence it relied on, how confident it was, and (once known) whether
it was actually right - plus a running reliability score per evidence
source built from that history.

    ledger_store.py     - sqlite CRUD (evidence_entries / source_reliability)
    evidence_ledger.py   - high-level API + FactCheckResult convenience wrapper

Usage:
    from intelligence.evidence_ledger import get_evidence_ledger
    ledger = get_evidence_ledger()
    entry = ledger.log_claim("...", "supported", 0.8, evidence=[...])
    ledger.record_outcome(entry["id"], "confirmed_true")

Purely additive - reasoning/fact_checker.py and reasoning/evidence.py
are unmodified; this only listens in on their output (see
ai/phase30_extended_tools.py's _check_fact for the hook).
"""

from intelligence.evidence_ledger.ledger_store import EvidenceLedgerStore, get_evidence_ledger_store
from intelligence.evidence_ledger.evidence_ledger import EvidenceLedger, get_evidence_ledger

__all__ = ["EvidenceLedgerStore", "get_evidence_ledger_store", "EvidenceLedger", "get_evidence_ledger"]
