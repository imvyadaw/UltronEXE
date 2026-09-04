"""
Intelligence (Phase 20.5)
=============================
Top-level package for ULTRON's intelligence layer. Houses:

    intelligence_core.py     - IntelligenceCore, the single top-level
                                entry point (process_turn()) tying
                                together every bridge intelligence_bridge/
                                (Phase 20.4) exposes. New in this phase.
    adaptive_performance/    - Phase 20.3, routing/caching/latency.
    predictive_preparation/  - Phase 20.2, what to have ready.
    proactive_intelligence/  - Phase 20.1, whether to speak up.

This __init__.py itself only re-exports intelligence_core.py's
IntelligenceCore/get_intelligence_core - it deliberately does not
import the phase-specific sub-packages above, so that importing
`intelligence` doesn't require all of them to be present or working.
Each is still fully usable on its own, e.g.:

    from intelligence.adaptive_performance import get_performance_engine

or, for a caller that wants every subsystem behind one uniform,
already-degrade-safe interface instead of importing sub-packages
directly:

    from intelligence import get_intelligence_core

    core = get_intelligence_core()
    result = core.process_turn("play some music")

Purely additive - existing imports of `intelligence.adaptive_performance`
etc. from earlier phases are unaffected by this file.
"""

from intelligence.intelligence_core import IntelligenceCore, get_intelligence_core

try:
    from database import DatabaseManager, get_database_manager
except Exception:  # pragma: no cover
    DatabaseManager = None
    get_database_manager = None

__all__ = [
    "IntelligenceCore",
    "get_intelligence_core",
    "DatabaseManager",
    "get_database_manager",
]
