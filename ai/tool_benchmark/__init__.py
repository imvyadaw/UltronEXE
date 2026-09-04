"""
Tool Benchmark (P4 - Automatic Tool Benchmarking & Reliability Scoring)
=========================================================================
Real per-call latency percentiles and degrading/improving trend
detection per tool, on top of raw samples kept in benchmark_store.py.
Complements (does not replace) ai/tool_chain_optimizer.py's cumulative
Bayesian success-score, which answers "which tool to pick" rather than
"how is this tool's real-world performance trending".

    benchmark_store.py       - sqlite CRUD for per-call samples
    tool_benchmark_engine.py - percentiles + trend + degrading-tools report

Usage:
    from ai.tool_benchmark import get_tool_benchmark_engine
    bench = get_tool_benchmark_engine()
    bench.record("web_search", duration_ms=340, success=True)
    bench.get_benchmark("web_search")
"""

from ai.tool_benchmark.benchmark_store import BenchmarkStore, get_benchmark_store
from ai.tool_benchmark.tool_benchmark_engine import ToolBenchmarkEngine, get_tool_benchmark_engine

__all__ = ["BenchmarkStore", "get_benchmark_store", "ToolBenchmarkEngine", "get_tool_benchmark_engine"]
