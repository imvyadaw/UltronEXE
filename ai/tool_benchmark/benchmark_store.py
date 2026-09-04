"""
Tool Benchmark Store (P4 - Automatic Tool Benchmarking & Reliability Scoring)
==============================================================================
Sqlite CRUD for per-call timing/outcome history. ai/tool_chain_optimizer.py
(P1) already keeps a cumulative Bayesian success-rate score per tool -
good for "which tool should I pick", but it doesn't keep individual
timing samples, so it can't answer "is this tool getting slower" or
"what's the p95 latency". This table is the raw sample log that
tool_benchmark_engine.py's percentile/trend math is built on.

Storage: database/tool_benchmark.db, table benchmark_calls.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "tool_benchmark.db"

_instance: Optional["BenchmarkStore"] = None
_instance_lock = threading.Lock()


class BenchmarkStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS benchmark_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT,
                duration_ms REAL,
                success INTEGER,
                timestamp REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_bench_tool ON benchmark_calls(tool_name)")
        self._conn.commit()

    def record(self, tool_name: str, duration_ms: float, success: bool) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO benchmark_calls (tool_name, duration_ms, success, timestamp) VALUES (?, ?, ?, ?)",
                (tool_name, duration_ms, 1 if success else 0, time.time()),
            )
            self._conn.commit()

    def get_recent_calls(self, tool_name: str, limit: int = 100) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT duration_ms, success, timestamp FROM benchmark_calls "
            "WHERE tool_name = ? ORDER BY timestamp DESC LIMIT ?",
            (tool_name, limit),
        ).fetchall()
        return [{"duration_ms": r[0], "success": bool(r[1]), "timestamp": r[2]} for r in rows]

    def get_all_tool_names(self) -> List[str]:
        rows = self._conn.execute("SELECT DISTINCT tool_name FROM benchmark_calls").fetchall()
        return [r[0] for r in rows]

    def get_call_count(self, tool_name: str) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM benchmark_calls WHERE tool_name = ?", (tool_name,)).fetchone()
        return row[0] if row else 0


def get_benchmark_store() -> BenchmarkStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = BenchmarkStore()
    return _instance
