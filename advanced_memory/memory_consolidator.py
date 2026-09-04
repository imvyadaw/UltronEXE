"""
Memory consolidator
====================
The "sleep cycle" - the one module that actually acts on what the
other six observe. Nothing else in ADVANCED_MEMORY prunes or promotes
anything on its own: episodic_memory.py exposes
consolidation_candidates(), forgetting_curve.py exposes
get_forgettable(), temporal_memory.py exposes detect_patterns() - all
read-only signals. run_cycle() here is where a decision actually gets
made, same separation self_critique_agent.py (judges) vs
autonomous_executor.py (acts) makes in PHASE_17_2_COGNITIVE_BRAIN.

One cycle, bounded like every other Phase 17 loop
(autonomous_executor.py caps at MAX_TOTAL_STEPS; this caps at
MAX_ITEMS_PER_CYCLE) so a huge backlog can't turn one run_cycle() call
into a runaway pass over the whole memory store:

    1. temporal_memory.detect_patterns() over the recent window
    2. promote strong/important episodes to semantic_memory (a new
       concept, with provenance back to the source event, confidence
       derived from retention - never overwrites a concept the user
       defined directly with confidence 1.0)
    3. prune weak, unpromoted episodes - "prune" only ever means
       dropping the graph node + forgetting_curve tracking record, so
       the advanced layer stops surfacing it in recall_similar()/graph
       traversal. The underlying memory/episodic_memory.py row is
       never touched - same non-destructive stance every prior Phase
       17 package takes toward the layer beneath it.

Reports through PHASE_17_1_FOUNDATION's unified bus as
"memory:consolidation_started" / "memory:promoted" / "memory:pruned" /
"memory:consolidation_complete", the same observability pattern
PHASE_17_2_COGNITIVE_BRAIN's context_bridge.py uses for "cognition:*".
"""

import time
from threading import Lock
from typing import Dict, Optional

from core_integration.phase16_bridge import get_bridge

from advanced_memory.memory_graph import get_memory_graph
from advanced_memory.forgetting_curve import get_forgetting_curve
from advanced_memory.episodic_memory import get_advanced_episodic_memory
from advanced_memory.semantic_memory import get_advanced_semantic_memory
from advanced_memory.temporal_memory import get_temporal_memory

MAX_ITEMS_PER_CYCLE = 50
DEFAULT_PROMOTE_IMPORTANCE = 0.7
DEFAULT_FORGET_THRESHOLD = 0.15
PROMOTION_BOOST_DAYS = 7.0  # protects a freshly-promoted episode from immediately re-qualifying as forgettable

_consolidator: Optional["MemoryConsolidator"] = None
_lock = Lock()


class MemoryConsolidator:
    """Do not construct directly - use get_consolidator()."""

    def __init__(self):
        self._bridge = get_bridge()
        self._graph = get_memory_graph()
        self._curve = get_forgetting_curve()
        self._episodic = get_advanced_episodic_memory()
        self._semantic = get_advanced_semantic_memory()
        self._temporal = get_temporal_memory()

    def run_cycle(
        self,
        lookback_days: int = 14,
        promote_importance: float = DEFAULT_PROMOTE_IMPORTANCE,
        forget_threshold: float = DEFAULT_FORGET_THRESHOLD,
        max_items: int = MAX_ITEMS_PER_CYCLE,
    ) -> Dict:
        """One bounded consolidation pass. Always returns a summary
        dict and never raises - a broken consolidation pass should
        degrade to "did nothing this cycle", not take down whatever
        scheduled it (same contract core.events.EventBus.emit() and
        PHASE_17_1's unified bus make for a broken subscriber)."""
        self._emit("consolidation_started", lookback_days=lookback_days)
        started = time.time()

        try:
            pattern_result = self._temporal.detect_patterns(lookback_days=lookback_days)
        except Exception as e:
            pattern_result = {"error": str(e)}

        promoted = self._promote_important_episodes(promote_importance, max_items)
        pruned = self._prune_forgettable_episodes(forget_threshold, max_items)
        legacy = self._run_legacy_layer_maintenance()

        summary = {
            "started_at": started,
            "duration_seconds": round(time.time() - started, 3),
            "patterns": pattern_result,
            "promoted_count": len(promoted),
            "promoted": promoted,
            "pruned_count": len(pruned),
            "pruned": pruned,
            "legacy_layer": legacy,
        }
        self._emit("consolidation_complete", promoted_count=len(promoted), pruned_count=len(pruned))
        return summary

    # -- legacy layer: learning/'s memory_consolidator.py + forgetting.py -----
    def _run_legacy_layer_maintenance(self) -> Dict:
        """This module consolidates the ADVANCED_MEMORY layer (events,
        importance, memory_graph). memory/episodic/'s older, still-active
        layer - task episodes with steps and a semantic pattern store -
        has its own parallel "sleep cycle" in learning/memory_consolidator.py
        (promote recurring/stale episodes into semantic patterns) and
        learning/forgetting.py (decay+prune those patterns and whatever
        episodes they've digested). Different data model, same job -
        rather than needing two separately-scheduled maintenance loops,
        one run_cycle() call here now runs both layers' passes. Best
        effort and strictly additive: neither legacy call can affect
        promoted/pruned above, and a missing or failing legacy layer just
        means this key reports its own error instead of the rest of the
        cycle failing."""
        result: Dict = {"consolidation": None, "decay": None}
        try:
            from learning.memory_consolidator import get_memory_consolidator

            result["consolidation"] = get_memory_consolidator().run_consolidation()
        except Exception as e:
            result["consolidation"] = {"error": str(e)}
        try:
            from learning.forgetting import get_forgetting

            result["decay"] = get_forgetting().run_decay_cycle()
        except Exception as e:
            result["decay"] = {"error": str(e)}
        return result

    # -- promotion: episodic -> semantic ---------------------------------------
    def _promote_important_episodes(self, min_importance: float, max_items: int) -> list:
        candidates_result = self._episodic.consolidation_candidates(min_importance=min_importance)
        if "error" in candidates_result:
            return []

        promoted = []
        for candidate in candidates_result["candidates"][:max_items]:
            event_id = candidate["event_id"]
            concept_label = _summarize_event_as_concept(candidate["event"])
            if not concept_label:
                continue

            existing = self._semantic.define(concept_label)
            if "error" not in existing and (existing.get("confidence") or 0) >= 1.0:
                # A concept the user defined directly outranks an inferred one - never overwrite it.
                continue

            retention_info = self._curve.retention(f"episodic:{event_id}")
            confidence = (
                round(min(0.95, 0.5 + candidate["importance"] * 0.4), 3)
                if "error" in retention_info
                else round(min(0.95, retention_info["retention"] * candidate["importance"] + 0.2), 3)
            )

            result = self._semantic.add_concept(
                concept_label,
                definition=candidate["event"],
                confidence=confidence,
                source_event_id=event_id,
            )
            if "error" in result:
                continue

            self._curve.boost(f"episodic:{event_id}", PROMOTION_BOOST_DAYS)
            self._emit("promoted", event_id=event_id, concept=concept_label, confidence=confidence)
            promoted.append({"event_id": event_id, "concept": concept_label, "confidence": confidence})

        return promoted

    # -- pruning: drop weak episodic nodes from the advanced layer -------------
    def _prune_forgettable_episodes(self, threshold: float, max_items: int) -> list:
        forgettable = self._curve.get_forgettable(threshold=threshold, ref_prefix="episodic:", limit=max_items)
        if "error" in forgettable:
            return []

        pruned = []
        for candidate in forgettable["candidates"]:
            memory_ref = candidate["memory_ref"]
            self._graph.delete_node(memory_ref)
            self._curve.forget(memory_ref)
            self._emit("pruned", memory_ref=memory_ref, retention=candidate["retention"])
            pruned.append(memory_ref)

        return pruned

    # -- observability -----------------------------------------------------------
    def _emit(self, stage: str, **payload) -> None:
        try:
            self._bridge.events.emit(f"memory:{stage}", **payload)
        except Exception:
            from core.error_trace import log_swallowed as _lsw

            _lsw("advanced_memory.memory_consolidator._emit")


def _summarize_event_as_concept(event_text: str) -> str:
    """Cheap, dependency-free label for a promoted concept - the first
    few words of the event, so "user asked to back up documents folder
    every friday" becomes concept "user asked to back up". Good enough
    to key a fact under; the full event text is kept as the definition,
    so nothing is lost even though the label is blunt."""
    words = event_text.strip().split()
    if not words:
        return ""
    return " ".join(words[:6]).lower()


def get_consolidator() -> MemoryConsolidator:
    """Process-wide singleton, same pattern as memory_graph.get_memory_graph()."""
    global _consolidator
    with _lock:
        if _consolidator is None:
            _consolidator = MemoryConsolidator()
        return _consolidator
