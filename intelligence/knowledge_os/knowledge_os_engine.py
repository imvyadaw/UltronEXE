"""
Knowledge OS Engine (P3 - Unified Personal Knowledge OS)
=========================================================
Ultron already scatters "what it knows" across several independent
systems: intelligence/knowledge_graph/ (entities + relations),
memory/semantic_memory.py (facts), memory/episodic_memory.py (events),
ai/rag_engine.py (retrieval over documents), intelligence/evidence_ledger/
(claim verdicts). Each is good at its own job, but there was no single
place to ask "what do you know about X" and get one answer merged
across all of them, tagged by source and freshness - a user re-asking
the same question three different ways could get three different
partial answers depending which subsystem happened to have the info.

This engine is that single front door. It keeps its own lightweight,
source-tagged fact ledger (knowledge_store.py) for facts explicitly
told to it, and on read (get_unified_view / search) best-effort
enriches with whatever the other subsystems can offer - each lookup
is wrapped so a subsystem being absent, empty, or erroring never
breaks the unified answer, it just contributes nothing.

Purely additive - none of knowledge_graph_engine.py, semantic_memory.py,
episodic_memory.py, or rag_engine.py are modified; this only reads
from them best-effort.
"""

import time
from typing import Dict, List, Optional

from intelligence.knowledge_os.knowledge_store import get_knowledge_store

# How old an own-ledger fact can get before get_freshness_report() flags
# it as worth re-verifying. A week is a reasonable default for personal
# facts (preferences, ongoing project state) that drift over time.
DEFAULT_STALE_AFTER_SECONDS = 7 * 24 * 3600


class KnowledgeOS:
    def __init__(self):
        self._store = get_knowledge_store()

    # -- own ledger ---------------------------------------------------
    def remember_fact(
        self, subject: str, fact_text: str, predicate: str = "is", source: str = "user", confidence: float = 0.8
    ) -> Dict:
        """Records a fact under (subject, predicate) from a named source.
        If another source already has a *different* fact_text for the
        same (subject, predicate), that's surfaced back to the caller
        as `conflicting_with` so it can be routed to the P4 Conflict
        Resolution Engine rather than silently overwritten - this
        ledger keeps one row per source on purpose so both survive."""
        existing = [
            f
            for f in self._store.get_facts_for_subject(subject)
            if f["predicate"] == (predicate or "is").strip().lower() and f["source"] != source
        ]
        conflicting = [f for f in existing if f["fact_text"].strip().lower() != fact_text.strip().lower()]
        fact = self._store.upsert_fact(subject, predicate, fact_text, source, confidence)
        result = dict(fact)
        if conflicting:
            result["conflicting_with"] = conflicting
        return result

    def get_own_facts(self, subject: str) -> List[Dict]:
        return self._store.get_facts_for_subject(subject)

    # -- unified read ---------------------------------------------------
    def get_unified_view(self, subject: str) -> Dict:
        """Single merged answer for 'what do you know about X', tagged
        by which subsystem each piece came from."""
        view = {"subject": subject, "sources": {}}

        own = self._store.get_facts_for_subject(subject)
        if own:
            view["sources"]["knowledge_os"] = own

        kg = self._best_effort_knowledge_graph(subject)
        if kg:
            view["sources"]["knowledge_graph"] = kg

        sem = self._best_effort_semantic_memory(subject)
        if sem:
            view["sources"]["semantic_memory"] = sem

        view["fact_count"] = sum(len(v) if isinstance(v, list) else 1 for v in view["sources"].values())
        return view

    def search(self, query: str, limit: int = 20) -> Dict:
        """Unified search - own ledger first (exact, source-tagged),
        then best-effort semantic memory as a fuzzier fallback."""
        own = self._store.search_facts(query, limit)
        sem = self._best_effort_semantic_search(query, limit)
        return {"query": query, "knowledge_os": own, "semantic_memory": sem}

    def get_freshness_report(self, max_age_seconds: float = DEFAULT_STALE_AFTER_SECONDS) -> Dict:
        """Facts in the own ledger old enough that they're worth
        re-confirming with the user rather than trusted blindly."""
        stale = self._store.get_stale_facts(max_age_seconds)
        return {
            "stale_count": len(stale),
            "max_age_days": round(max_age_seconds / 86400, 1),
            "stale_facts": [
                {
                    "subject": f["subject"],
                    "fact_text": f["fact_text"],
                    "source": f["source"],
                    "age_days": round((time.time() - f["updated_at"]) / 86400, 1),
                }
                for f in stale
            ],
        }

    def get_known_subjects(self) -> List[str]:
        return self._store.get_all_subjects()

    # -- best-effort enrichment (never raises) ----------------------------
    @staticmethod
    def _best_effort_knowledge_graph(subject: str) -> Optional[List[Dict]]:
        try:
            from intelligence.knowledge_graph.knowledge_graph_engine import get_knowledge_graph_engine

            engine = get_knowledge_graph_engine()
            if hasattr(engine, "query"):
                result = engine.query(subject)
            elif hasattr(engine, "search"):
                result = engine.search(subject)
            else:
                return None
            return result or None
        except Exception:
            return None

    @staticmethod
    def _best_effort_semantic_memory(subject: str) -> Optional[List[Dict]]:
        try:
            from memory.semantic_memory import SemanticMemory

            mem = SemanticMemory()
            if hasattr(mem, "search"):
                result = mem.search(subject)
            elif hasattr(mem, "recall"):
                result = mem.recall(subject)
            else:
                return None
            return result or None
        except Exception:
            return None

    @staticmethod
    def _best_effort_semantic_search(query: str, limit: int) -> Optional[List[Dict]]:
        try:
            from memory.semantic_memory import SemanticMemory

            mem = SemanticMemory()
            if hasattr(mem, "search"):
                return mem.search(query, limit=limit) or None
        except Exception:
            return None
        return None


_instance: Optional[KnowledgeOS] = None


def get_knowledge_os() -> KnowledgeOS:
    global _instance
    if _instance is None:
        _instance = KnowledgeOS()
    return _instance
