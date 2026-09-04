"""
Advanced semantic memory
=========================
memory/semantic_memory.py already stores concept definitions and
single-hop relations (concept --relation--> related_concept) in
SQLite - unchanged and reused here as-is. What's added:

    - confidence per concept (a fact told directly by the user should
      outrank one memory_consolidator.py inferred from a single
      episode) and, when known, provenance back to the episodic event
      that taught it (episodic_memory.py's "episodic:<id>" node)
    - every add_concept()/relate() call is mirrored into
      memory_graph.py, so relations aren't limited to one hop the way
      SemanticMemory.get_related() is - related_concepts(depth=2) can
      answer "what's indirectly connected to X" by walking the shared
      graph that episodic/spatial/temporal memory also write into

This module owns one extra table (concept -> confidence/source, in its
own DB) and never touches memory/semantic_memory.py's schema.
"""

import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from memory.semantic_memory import SemanticMemory

from advanced_memory.memory_graph import get_memory_graph
from advanced_memory.forgetting_curve import get_forgetting_curve

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "advanced_semantic_memory.db"

_advanced_semantic: Optional["AdvancedSemanticMemory"] = None
_lock = Lock()


class AdvancedSemanticMemory:
    """Do not construct directly - use get_advanced_semantic_memory()."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS concept_meta (
                concept TEXT PRIMARY KEY,
                confidence REAL,
                source_event_id INTEGER,
                created_at REAL
            )""")
        self._conn.commit()
        self._write_lock = Lock()

        self._base = SemanticMemory()
        self._graph = get_memory_graph()
        self._curve = get_forgetting_curve()

    # -- writing ---------------------------------------------------------------
    def add_concept(
        self, concept: str, definition: str, confidence: float = 0.8, source_event_id: Optional[int] = None
    ) -> Dict:
        """Define/redefine a concept. `confidence` in [0, 1]: 1.0 for
        something the user stated outright, lower for something
        memory_consolidator.py inferred from a pattern. `source_event_id`
        links back to the episodic_memory.py event this was learned
        from, if any."""
        base_result = self._base.add_concept(concept, definition)
        if "error" in base_result:
            return base_result

        confidence = max(0.0, min(1.0, confidence))
        node_id = f"concept:{concept.lower()}"
        try:
            with self._write_lock:
                self._conn.execute(
                    "INSERT INTO concept_meta (concept, confidence, source_event_id, created_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(concept) DO UPDATE SET confidence = excluded.confidence, source_event_id = excluded.source_event_id",
                    (concept.lower(), confidence, source_event_id, time.time()),
                )
                self._conn.commit()
        except Exception as e:
            return {"error": str(e)}

        self._graph.add_node(
            node_id, "semantic", concept, metadata={"definition": definition, "confidence": confidence}
        )
        self._curve.track(node_id, importance=confidence)
        if source_event_id is not None:
            self._graph.add_edge(f"episodic:{source_event_id}", node_id, "taught")

        return {**base_result, "confidence": confidence, "node_id": node_id}

    def relate(self, concept: str, relation: str, related_concept: str, confidence: float = 0.8) -> Dict:
        """Store a relation via the base module, and mirror it as a
        graph edge so related_concepts() can traverse past one hop."""
        base_result = self._base.relate(concept, relation, related_concept)
        if "error" in base_result:
            return base_result
        self._graph.add_edge(
            f"concept:{concept.lower()}", f"concept:{related_concept.lower()}", relation, weight=confidence
        )
        return base_result

    # -- reading -----------------------------------------------------------------
    def define(self, concept: str) -> Dict:
        result = self._base.define(concept)
        if "error" in result:
            return result
        node_id = f"concept:{concept.lower()}"
        self._curve.record_access(node_id)
        result["confidence"] = self._get_confidence(concept)
        return result

    def get_related(self, concept: str) -> Dict:
        """One-hop relations, straight from the base module - unchanged."""
        return self._base.get_related(concept)

    def related_concepts(self, concept: str, depth: int = 2) -> Dict:
        """Multi-hop traversal over the shared graph - concepts reachable
        within `depth` hops, whether the connection is a direct
        SemanticMemory relation or via an episodic/spatial/temporal node
        in between. depth=1 matches get_related() but returns node_ids
        instead of raw relation rows."""
        node_id = f"concept:{concept.lower()}"
        seen = {node_id}
        frontier = [node_id]
        found: List[Dict] = []
        try:
            for hop in range(1, depth + 1):
                next_frontier = []
                for current in frontier:
                    nb = self._graph.neighbors(current, direction="both")
                    if "error" in nb:
                        continue
                    for edge in nb["neighbors"]:
                        target = edge["node_id"]
                        if target in seen:
                            continue
                        seen.add(target)
                        next_frontier.append(target)
                        found.append({"node_id": target, "relation": edge["relation"], "hops": hop})
                frontier = next_frontier
                if not frontier:
                    break
            return {"concept": concept, "depth": depth, "count": len(found), "related": found}
        except Exception as e:
            return {"error": str(e)}

    def search_concepts(self, query: str) -> Dict:
        return self._base.search_concepts(query)

    def high_confidence_concepts(self, min_confidence: float = 0.7) -> Dict:
        """Concepts worth trusting without double-checking - e.g. for
        prompt_manager.py-style context injection where a shaky,
        single-episode inference shouldn't be presented as settled fact."""
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT concept, confidence, source_event_id FROM concept_meta WHERE confidence >= ? ORDER BY confidence DESC",
                (min_confidence,),
            )
            rows = cur.fetchall()
            concepts = [{"concept": r[0], "confidence": r[1], "source_event_id": r[2]} for r in rows]
            return {"count": len(concepts), "concepts": concepts}
        except Exception as e:
            return {"error": str(e)}

    # -- internal --------------------------------------------------------------
    def _get_confidence(self, concept: str) -> Optional[float]:
        cur = self._conn.cursor()
        cur.execute("SELECT confidence FROM concept_meta WHERE concept = ?", (concept.lower(),))
        row = cur.fetchone()
        return row[0] if row else None


def get_advanced_semantic_memory() -> AdvancedSemanticMemory:
    """Process-wide singleton, same pattern as memory_graph.get_memory_graph()."""
    global _advanced_semantic
    with _lock:
        if _advanced_semantic is None:
            _advanced_semantic = AdvancedSemanticMemory()
        return _advanced_semantic
