"""
Conflict Resolution Engine (P4)
================================
Detects and resolves disagreements between two sources' claims about
the same subject - something no existing module does. Feeds off two
P2/P3 systems on a best-effort basis without depending on either
being present:

    intelligence/evidence_ledger/  - per-source reliability score, used
                                      to auto-resolve when one source
                                      has a meaningfully better track
                                      record
    intelligence/knowledge_os/     - remember_fact() already surfaces
                                      same-subject disagreements via its
                                      `conflicting_with` field; callers
                                      route those here via detect_conflict()

auto_resolve() only ever picks a winner when the reliability gap is
clear (>= AUTO_RESOLVE_MARGIN) and both sources have enough judged
history to trust the score - otherwise it leaves the conflict open
for manual_resolve(), same "don't guess past what the evidence
supports" posture as intelligence/evidence_ledger/.
"""

import time
from typing import Dict, List, Optional

from intelligence.conflict_resolution.conflict_store import get_conflict_store

AUTO_RESOLVE_MARGIN = 0.15
MIN_JUDGED_CITATIONS = 2


class ConflictResolver:
    def __init__(self):
        self._store = get_conflict_store()

    def detect_conflict(self, subject: str, claim_a: str, source_a: str, claim_b: str, source_b: str) -> Dict:
        if claim_a.strip().lower() == claim_b.strip().lower():
            return {"conflict_logged": False, "reason": "claims match, no conflict"}
        conflict = self._store.log_conflict(subject, claim_a, source_a, claim_b, source_b)
        return {"conflict_logged": True, "conflict": conflict}

    def auto_resolve(self, conflict_id: str) -> Dict:
        conflict = self._store.get_conflict(conflict_id)
        if not conflict:
            return {"resolved": False, "reason": "conflict not found"}
        if conflict["status"] != "open":
            return {"resolved": False, "reason": f"conflict already {conflict['status']}"}

        score_a = self._best_effort_source_reliability(conflict["source_a"])
        score_b = self._best_effort_source_reliability(conflict["source_b"])

        if score_a is None or score_b is None:
            return {
                "resolved": False,
                "reason": "no reliability history for one or both sources; leave for manual review",
            }

        judged_a = score_a.get("times_correct", 0) + score_a.get("times_wrong", 0)
        judged_b = score_b.get("times_correct", 0) + score_b.get("times_wrong", 0)
        if judged_a < MIN_JUDGED_CITATIONS or judged_b < MIN_JUDGED_CITATIONS:
            return {"resolved": False, "reason": "not enough judged history on one or both sources to auto-resolve"}

        gap = abs(score_a["reliability_score"] - score_b["reliability_score"])
        if gap < AUTO_RESOLVE_MARGIN:
            return {"resolved": False, "reason": f"reliability gap too small ({gap:.2f}) to auto-resolve confidently"}

        winner = (
            conflict["source_a"]
            if score_a["reliability_score"] > score_b["reliability_score"]
            else conflict["source_b"]
        )
        self._store.resolve(
            conflict_id,
            resolution="auto: higher source reliability",
            resolved_source=winner,
            note=f"{conflict['source_a']}={score_a['reliability_score']:.2f} vs "
            f"{conflict['source_b']}={score_b['reliability_score']:.2f}",
        )
        return {"resolved": True, "winner": winner, "conflict_id": conflict_id}

    def manual_resolve(self, conflict_id: str, resolved_source: str, note: str = "") -> Dict:
        success = self._store.resolve(conflict_id, resolution="manual", resolved_source=resolved_source, note=note)
        return {"resolved": success, "conflict_id": conflict_id, "resolved_source": resolved_source}

    def list_open_conflicts(self, subject: Optional[str] = None) -> List[Dict]:
        return self._store.get_open_conflicts(subject)

    def get_conflict_report(self, limit: int = 20) -> Dict:
        recent = self._store.get_recent(limit)
        open_count = sum(1 for c in recent if c["status"] == "open")
        return {"open_count": open_count, "recent": recent, "checked_at": time.time()}

    @staticmethod
    def _best_effort_source_reliability(source: str) -> Optional[Dict]:
        try:
            from intelligence.evidence_ledger import get_evidence_ledger

            return get_evidence_ledger().get_source_reliability(source)
        except Exception:
            return None


_instance: Optional[ConflictResolver] = None


def get_conflict_resolver() -> ConflictResolver:
    global _instance
    if _instance is None:
        _instance = ConflictResolver()
    return _instance
