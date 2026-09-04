"""
Performance Bridge (Phase 20.4 - Intelligence Bridge)
==================================================
Bridge onto intelligence.adaptive_performance (Phase 20.3) - unlike
the other 12 bridges in this package, adaptive_performance/'s full
source shipped alongside this phase, so this one wires directly to
its real, known API (PerformanceEngine.plan_call()/record_call()/
register_operation(), plus each sub-module's own get_x() singleton)
instead of the name/keyword discovery the rest of this package falls
back to. It still never raises past this boundary - every method
degrades to a safe default if adaptive_performance/ turns out to be
missing from a given checkout, same posture as every other bridge
here, for a caller that wants to treat all 13 uniformly.

Usage:
    from intelligence_bridge.performance_bridge import get_performance_bridge

    pb = get_performance_bridge()
    if pb.is_available():
        pb.register_operation("chat_completion", ["openai", "anthropic", "local_llama"])
        plan = pb.plan_call("chat_completion", cache_key=prompt_hash)
        if not plan["cache_hit"]:
            ...  # call plan["provider"], then pb.record_call(...)

Purely additive - does not modify adaptive_performance/ and imports
nothing from proactive_bridge.py/predictive_bridge.py, mirroring
performance_engine.py's own "doesn't import from Phase 20.1/20.2"
stance one layer up.
"""

from typing import Any, Dict, List, Optional

from intelligence_bridge._bridge_utils import logger, safe_call

try:
    from intelligence.adaptive_performance import (
        get_performance_engine,
        get_latency_tracker,
        get_provider_analyzer,
        get_path_optimizer,
        get_cache_strategist,
        get_auto_optimizer,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - only hit if 20.3 isn't present
    get_performance_engine = None
    get_latency_tracker = None
    get_provider_analyzer = None
    get_path_optimizer = None
    get_cache_strategist = None
    get_auto_optimizer = None
    _IMPORT_ERROR = exc


class PerformanceBridge:
    """Bridges to intelligence.adaptive_performance (Phase 20.3)."""

    def __init__(self):
        self._engine = None
        self._latency = None
        self._analyzer = None
        self._paths = None
        self._cache = None
        self._auto = None

        if get_performance_engine is not None:
            try:
                self._engine = get_performance_engine()
                self._latency = get_latency_tracker()
                self._analyzer = get_provider_analyzer()
                self._paths = get_path_optimizer()
                self._cache = get_cache_strategist()
                self._auto = get_auto_optimizer()
                logger.info("[performance_bridge] connected to intelligence.adaptive_performance")
            except Exception:
                logger.exception("[performance_bridge] adaptive_performance imported but failed to initialize")
                self._engine = None
        else:
            logger.info(
                "[performance_bridge] intelligence.adaptive_performance not found (%s) - "
                "running in degraded/no-op mode",
                _IMPORT_ERROR,
            )

    def is_available(self) -> bool:
        return self._engine is not None

    def status(self) -> Dict[str, Any]:
        return {
            "bridge": "performance",
            "available": self.is_available(),
            "source_module": "intelligence.adaptive_performance" if self.is_available() else None,
        }

    # -- PerformanceEngine passthrough (the two calls most callers need) --

    def register_operation(self, operation: str, providers: List[str]) -> bool:
        """One-time setup wiring `operation` into path_optimizer.py's
        candidates and auto_optimizer.py's sweep list."""
        if not self.is_available():
            return False
        return safe_call(self._engine, "register_operation", operation, providers, default=_MISSING) is not _MISSING

    def plan_call(
        self, operation: str, cache_key: Optional[str] = None, context: Optional[Dict] = None
    ) -> Optional[Dict]:
        """Call before making a real provider call - returns a cached
        value on a hit, otherwise the provider to use. None (not a
        dict) if adaptive_performance/ isn't available at all, so a
        caller can tell "no engine" apart from a real decision."""
        if not self.is_available():
            return None
        return safe_call(self._engine, "plan_call", operation, cache_key=cache_key, context=context)

    def record_call(
        self,
        call_id: str,
        operation: str,
        provider: str,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        cache_key: Optional[str] = None,
        value: Optional[Any] = None,
    ) -> Optional[Dict]:
        """Call after a real provider call finishes - always logs to
        latency_tracker.py, stores to cache_strategist.py if warranted."""
        if not self.is_available():
            return None
        return safe_call(
            self._engine,
            "record_call",
            call_id,
            operation,
            provider,
            latency_ms,
            success=success,
            error=error,
            cache_key=cache_key,
            value=value,
        )

    def get_operation_summary(self, operation: str) -> Optional[Dict]:
        """Ranked providers + cache hit rate/TTL + recent path decisions
        for `operation`, per PerformanceEngine.get_operation_summary()."""
        if not self.is_available():
            return None
        return safe_call(self._engine, "get_operation_summary", operation)

    def get_recent_events(self, operation: Optional[str] = None, limit: int = 20) -> List[Dict]:
        if not self.is_available():
            return []
        return safe_call(self._engine, "get_recent_events", operation=operation, limit=limit, default=[])

    # -- direct sub-module access, for a caller that wants just one piece --

    def get_stats(
        self, provider: Optional[str] = None, operation: Optional[str] = None, window_seconds: Optional[float] = None
    ) -> Optional[Dict]:
        """Raw latency/success-rate stats straight from latency_tracker.py."""
        if self._latency is None:
            return None
        return safe_call(
            self._latency, "get_stats", provider=provider, operation=operation, window_seconds=window_seconds
        )

    def rank_providers(self, providers: List[str], operation: Optional[str] = None) -> List[Dict]:
        """Scored/ranked providers straight from provider_analyzer.py."""
        if self._analyzer is None:
            return []
        return safe_call(self._analyzer, "rank_providers", providers, operation=operation, default=[])

    def choose_path(self, operation: str, context: Optional[Dict] = None) -> Optional[Dict]:
        """Provider choice + fallback order straight from path_optimizer.py,
        without going through the cache check plan_call() does first."""
        if self._paths is None:
            return None
        return safe_call(self._paths, "choose_path", operation, context=context)

    def get_hit_rate(self, operation: str) -> Optional[float]:
        """Cache hit rate straight from cache_strategist.py."""
        if self._cache is None:
            return None
        return safe_call(self._cache, "get_hit_rate", operation)

    def run_optimization_pass(self) -> Optional[Any]:
        """Manually trigger one auto_optimizer.py sweep instead of
        waiting for its own schedule/start_background()."""
        if self._auto is None:
            return None
        return safe_call(self._auto, "run_pass")

    def call(self, method_name: str, *args, **kwargs) -> Optional[Any]:
        """Generic passthrough to the PerformanceEngine for anything not
        covered above."""
        return safe_call(self._engine, method_name, *args, **kwargs)


_MISSING = object()
_bridge_instance: Optional[PerformanceBridge] = None


def get_performance_bridge() -> PerformanceBridge:
    """Process-wide PerformanceBridge singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = PerformanceBridge()
    return _bridge_instance
