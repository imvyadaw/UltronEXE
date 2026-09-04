"""
Tool Benchmark Engine (P4 - Automatic Tool Benchmarking & Reliability Scoring)
================================================================================
ai/tool_chain_optimizer.py (P1) answers "which tool, of these
candidates, is more likely to succeed" with a single cumulative
Bayesian score. This engine answers a different question: "how is
THIS tool actually performing, in latency and success rate, and is
that changing over time" - real percentiles (p50/p95) and a
recent-vs-previous-window trend, computed from ai/tool_benchmark/
benchmark_store.py's raw per-call samples.

record() is meant to be called from the same place tool_chain_optimizer's
own stats get recorded (core/action_pipeline.py stage 5) - purely
additive logging, never blocking. get_degrading_tools() is what a
caller (or a self-health-check pass) would actually act on.
"""

from typing import Dict, List, Optional

from ai.tool_benchmark.benchmark_store import get_benchmark_store

TREND_WINDOW = 20  # split the most recent N calls in half to compare trend


class ToolBenchmarkEngine:
    def __init__(self):
        self._store = get_benchmark_store()

    def record(self, tool_name: str, duration_ms: float, success: bool) -> None:
        self._store.record(tool_name, duration_ms, success)

    def get_benchmark(self, tool_name: str) -> Dict:
        calls = self._store.get_recent_calls(tool_name, limit=200)
        if not calls:
            return {"tool_name": tool_name, "samples": 0}

        durations = sorted(c["duration_ms"] for c in calls)
        n = len(durations)
        p50 = durations[int(0.50 * (n - 1))]
        p95 = durations[int(0.95 * (n - 1))]
        avg = sum(durations) / n
        success_rate = sum(1 for c in calls if c["success"]) / n

        trend = self._compute_trend(calls)

        return {
            "tool_name": tool_name,
            "samples": n,
            "avg_ms": round(avg, 1),
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "success_rate": round(success_rate, 3),
            "trend": trend,
        }

    @staticmethod
    def _compute_trend(calls_desc: List[Dict]) -> str:
        """calls_desc is most-recent-first. Compare the newer half of
        the trend window against the older half on both latency and
        success rate - flags degrading only if BOTH latency got worse
        and success rate dropped, so a single slow-but-fine call
        doesn't trip a false alarm."""
        window = calls_desc[:TREND_WINDOW]
        if len(window) < 10:
            return "insufficient_data"
        half = len(window) // 2
        newer, older = window[:half], window[half:]
        newer_avg_ms = sum(c["duration_ms"] for c in newer) / len(newer)
        older_avg_ms = sum(c["duration_ms"] for c in older) / len(older)
        newer_success = sum(1 for c in newer if c["success"]) / len(newer)
        older_success = sum(1 for c in older if c["success"]) / len(older)

        slower = newer_avg_ms > older_avg_ms * 1.25
        less_reliable = newer_success < older_success - 0.15
        faster = newer_avg_ms < older_avg_ms * 0.75
        more_reliable = newer_success > older_success + 0.15

        if slower and less_reliable:
            return "degrading"
        if faster or more_reliable:
            return "improving"
        return "stable"

    def get_report(self, limit: int = 20) -> Dict:
        names = self._store.get_all_tool_names()
        benchmarks = [self.get_benchmark(n) for n in names]
        benchmarks.sort(key=lambda b: b.get("samples", 0), reverse=True)
        return {"tools": benchmarks[:limit], "total_tracked": len(names)}

    def get_degrading_tools(self) -> List[Dict]:
        names = self._store.get_all_tool_names()
        benchmarks = [self.get_benchmark(n) for n in names]
        return [b for b in benchmarks if b.get("trend") == "degrading"]


_instance: Optional[ToolBenchmarkEngine] = None


def get_tool_benchmark_engine() -> ToolBenchmarkEngine:
    global _instance
    if _instance is None:
        _instance = ToolBenchmarkEngine()
    return _instance
