"""
ADVANCED_MEMORY
================
    memory_graph.py         - typed node/edge store every other module
                               here mirrors itself into ("episodic:<id>",
                               "concept:<name>", "place:<id>", "routine:<id>")
    forgetting_curve.py      - Ebbinghaus-style decay/strength tracking;
                               read-only signal, never prunes anything itself
    episodic_memory.py       - wraps memory/episodic_memory.py: importance,
                               graph nodes, embedding-backed recall_similar()
    semantic_memory.py       - wraps memory/semantic_memory.py: confidence,
                               provenance, multi-hop related_concepts()
    spatial_memory.py        - named places (geo/filesystem/app/network) and
                               what episodic events happened where
    temporal_memory.py       - recurring-routine detection over episodic
                               events, plus resolve_relative_time()
    memory_consolidator.py   - the only module that acts: bounded cycle that
                               promotes strong episodes to semantic memory
                               and prunes weak ones from the advanced layer

Import order: memory_graph.py and forgetting_curve.py have no
dependency on anything else here; episodic_memory.py, semantic_memory.py,
spatial_memory.py and temporal_memory.py each depend on those two (and,
for episodic/semantic/temporal, on the pre-existing memory/ modules they
wrap) but not on each other; memory_consolidator.py depends on all five.

Nothing in memory/, core/, ai/, agents/, main.py,
PHASE_17_1_FOUNDATION/ or PHASE_17_2_COGNITIVE_BRAIN/ imports anything
from here - purely additive, same guarantee every prior Phase 17
package makes. memory_consolidator.py imports
core_integration.phase16_bridge to emit
"memory:*" events on the unified bus, the same one-way relationship
PHASE_17_2_COGNITIVE_BRAIN's context_bridge.py has with it.
"""

from advanced_memory.memory_graph import get_memory_graph
from advanced_memory.forgetting_curve import get_forgetting_curve
from advanced_memory.episodic_memory import get_advanced_episodic_memory
from advanced_memory.semantic_memory import get_advanced_semantic_memory
from advanced_memory.spatial_memory import get_spatial_memory
from advanced_memory.temporal_memory import get_temporal_memory, resolve_relative_time
from advanced_memory.memory_consolidator import get_consolidator

__all__ = [
    "get_memory_graph",
    "get_forgetting_curve",
    "get_advanced_episodic_memory",
    "get_advanced_semantic_memory",
    "get_spatial_memory",
    "get_temporal_memory",
    "resolve_relative_time",
    "get_consolidator",
]
