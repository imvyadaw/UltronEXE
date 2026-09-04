"""
Self Healing (Phase 19.5)
=============================
Closes the loop after Phase 19.4's verification: when an action
fails (or verification says it didn't really work), this package
diagnoses why, proposes recovery strategies, retries with backoff,
falls back to alternate actions, and remembers what actually fixed
it for next time - backed by a shared database at
database/self_healing.db:

    failure_diagnoser.py   - classifies a failure (exception/error
                              text/failed verification checks) into
                              a category + stable signature
    strategy_generator.py  - category -> ordered candidate recovery
                              strategies, with any previously-proven
                              fix for this signature bumped to front
    retry_manager.py       - per-key retry attempt count + exponential
                              backoff gate, persisted across restarts
    fallback_chain.py      - registry of alternate actions to try
                              once an action's own strategies are
                              exhausted
    healing_memory.py      - records which strategy worked/failed per
                              failure signature
    self_healing_engine.py - single entry point tying all of the
                              above together

Usage:
    from intelligence.self_healing import get_self_healing_engine
    she = get_self_healing_engine()

    # advisory mode - just get the plan, don't execute anything
    plan = she.heal("send_report", error="Connection refused")

    # active mode - actually drive recovery
    def executor(strategy_name):
        ...  # perform strategy_name, return True/False
    result = she.heal("send_report", error="Connection refused", executor=executor)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through the top-level engine.

Purely additive - nothing in Phase 1-19.4 imports from here.
"""

from intelligence.self_healing.failure_diagnoser import FailureDiagnoser, get_failure_diagnoser
from intelligence.self_healing.strategy_generator import StrategyGenerator, get_strategy_generator
from intelligence.self_healing.retry_manager import RetryManager, get_retry_manager
from intelligence.self_healing.fallback_chain import FallbackChain, get_fallback_chain
from intelligence.self_healing.healing_memory import HealingMemory, get_healing_memory
from intelligence.self_healing.self_healing_engine import SelfHealingEngine, get_self_healing_engine

__all__ = [
    "SelfHealingEngine",
    "get_self_healing_engine",
    "FailureDiagnoser",
    "get_failure_diagnoser",
    "StrategyGenerator",
    "get_strategy_generator",
    "RetryManager",
    "get_retry_manager",
    "FallbackChain",
    "get_fallback_chain",
    "HealingMemory",
    "get_healing_memory",
]
