"""
Adaptive Performance (Phase 20.3)
=============================
ULTRON learning which provider is fastest/most reliable for a given
kind of call, and adapting its routing and caching accordingly - as
opposed to Phase 20.2's predictive_preparation/, which decides what
to have *ready*, or Phase 20.1's proactive_intelligence/, which
decides whether to *say* something. This package never chooses what
work to do; it only makes the work ULTRON already does faster and
more reliable over time, invisibly:

    latency_tracker.py   - ground truth. record() logs every call's
                            latency and success/failure; get_stats()
                            answers with count/avg/p50/p95/p99/
                            success_rate. Owns table `latency_events`.
    provider_analyzer.py - turns latency_tracker.py's raw log into a
                            score per provider (blend of success_rate
                            and latency) plus a trend
                            (improving/stable/degrading). Owns table
                            `provider_snapshots`.
    path_optimizer.py    - chooses which registered provider should
                            handle an operation right now, with
                            hysteresis so near-tied scores don't cause
                            flapping. Owns table `path_decisions`.
    cache_strategist.py  - decides whether a result is worth caching,
                            holds the in-memory cache, and adapts each
                            operation's TTL from its own hit rate.
                            Owns table `cache_events`.
    auto_optimizer.py    - periodically sweeps registered operations,
                            re-running path_optimizer.py's choice and
                            cache_strategist.py's TTL tuning so both
                            drift correctly even without live traffic.
                            Owns table `optimization_actions`.
    performance_engine.py - single entry point tying all of the above
                            together; owns table `performance_events`.

Usage:
    from intelligence.adaptive_performance import get_performance_engine

    engine = get_performance_engine()

    # one-time setup elsewhere in ULTRON - nothing is registered by default:
    engine.register_operation("chat_completion", ["openai", "anthropic", "local_llama"])

    # normal use - one call before, one call after:
    plan = engine.plan_call("chat_completion", cache_key=prompt_hash)
    if plan["cache_hit"]:
        result = plan["value"]
    else:
        t0 = time.time()
        result = call_provider(plan["provider"], ...)
        engine.record_call(plan["call_id"], "chat_completion", plan["provider"],
                            latency_ms=(time.time() - t0) * 1000, success=True,
                            cache_key=prompt_hash, value=result)

Each sub-module also exposes its own get_x() singleton and can be
used directly - e.g. call latency_tracker.py alone just to log/query
raw call performance, with no routing or caching involved.

Purely additive - nothing in Phase 1-20 imports from here, and this
package does not import from predictive_preparation/ (Phase 20.2) or
proactive_intelligence/ (Phase 20.1). Registration
(register_operation/register_operation_providers) is left to whichever
caller elsewhere in ULTRON owns that provider list - this package
ships with empty registries and tracks/scores regardless, it just has
nothing to route or auto-tune until something is registered.
"""

from intelligence.adaptive_performance.latency_tracker import LatencyTracker, get_latency_tracker
from intelligence.adaptive_performance.provider_analyzer import ProviderAnalyzer, get_provider_analyzer
from intelligence.adaptive_performance.path_optimizer import PathOptimizer, get_path_optimizer
from intelligence.adaptive_performance.cache_strategist import CacheStrategist, get_cache_strategist
from intelligence.adaptive_performance.auto_optimizer import AutoOptimizer, get_auto_optimizer
from intelligence.adaptive_performance.performance_engine import PerformanceEngine, get_performance_engine

__all__ = [
    "PerformanceEngine",
    "get_performance_engine",
    "LatencyTracker",
    "get_latency_tracker",
    "ProviderAnalyzer",
    "get_provider_analyzer",
    "PathOptimizer",
    "get_path_optimizer",
    "CacheStrategist",
    "get_cache_strategist",
    "AutoOptimizer",
    "get_auto_optimizer",
]
