"""
Memory graph
============
The connective tissue for PHASE_17_3_MEMORY_SYSTEM: a typed node/edge
store so episodic_memory.py, semantic_memory.py, spatial_memory.py and
temporal_memory.py stop being four islands and become one queryable
graph - "which places was I at during the episodes that taught me this
concept" is a 3-hop traversal here, not four separate lookups the
caller has to stitch together by hand.

Deliberately generic: this file has zero knowledge of episodes,
concepts, places or routines. Every other ADVANCED_MEMORY module
registers its own rows elsewhere (its own SQLite table, exactly like
memory/episodic_memory.py and memory/semantic_memory.py already do)
and *also* mirrors a lightweight node here - `node_id` is always
"<memory_type>:<local_id>" (e.g. "episodic:42", "concept:vpn",
"place:home") so a graph node can always be traced back to the record
that owns it, but this module never touches that record itself.

Nothing in memory/, core/, ai/, agents/, PHASE_17_1_FOUNDATION/ or
PHASE_17_2_COGNITIVE_BRAIN/ imports this or is imported by it - purely
additive, same guarantee every prior Phase 17 package makes.
"""

import json
import sqlite3
import time
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "storage" / "sqlite" / "memory_graph.db"

_graph: Optional["MemoryGraph"] = None
_lock = Lock()


class MemoryGraph:
    """Typed nodes + typed, weighted edges between them. Do not
    construct directly - use get_memory_graph()."""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT,
                label TEXT,
                metadata TEXT,
                created_at REAL,
                updated_at REAL
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT,
                to_id TEXT,
                relation TEXT,
                weight REAL,
                created_at REAL
            )""")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type)")
        self._conn.commit()
        self._write_lock = Lock()

    # -- nodes ---------------------------------------------------------------
    def add_node(self, node_id: str, node_type: str, label: str, metadata: Optional[Dict] = None) -> Dict:
        """Create or update a node. Safe to call every time a memory is
        written - upserts, never duplicates."""
        try:
            now = time.time()
            with self._write_lock:
                self._conn.execute(
                    "INSERT INTO nodes (node_id, node_type, label, metadata, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(node_id) DO UPDATE SET label = excluded.label, "
                    "metadata = excluded.metadata, updated_at = excluded.updated_at",
                    (node_id, node_type, label, json.dumps(metadata or {}), now, now),
                )
                self._conn.commit()
            return {"success": True, "node_id": node_id, "node_type": node_type}
        except Exception as e:
            return {"error": str(e)}

    def get_node(self, node_id: str) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT node_id, node_type, label, metadata, created_at, updated_at FROM nodes WHERE node_id = ?",
                (node_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": f"No node '{node_id}'"}
            return {
                "node_id": row[0],
                "node_type": row[1],
                "label": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
                "created_at": row[4],
                "updated_at": row[5],
            }
        except Exception as e:
            return {"error": str(e)}

    def nodes_by_type(self, node_type: str, limit: int = 100) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT node_id, label, metadata, created_at FROM nodes WHERE node_type = ? ORDER BY updated_at DESC LIMIT ?",
                (node_type, limit),
            )
            rows = cur.fetchall()
            nodes = [
                {"node_id": r[0], "label": r[1], "metadata": json.loads(r[2]) if r[2] else {}, "created_at": r[3]}
                for r in rows
            ]
            return {"node_type": node_type, "count": len(nodes), "nodes": nodes}
        except Exception as e:
            return {"error": str(e)}

    def search_nodes(self, query: str, node_type: Optional[str] = None, limit: int = 50) -> Dict:
        """Substring search over node labels - same lightweight approach
        as memory/semantic_memory.py's search_concepts(), not a
        replacement for vector similarity search."""
        try:
            like = f"%{query.lower()}%"
            cur = self._conn.cursor()
            if node_type:
                cur.execute(
                    "SELECT node_id, node_type, label FROM nodes WHERE lower(label) LIKE ? AND node_type = ? LIMIT ?",
                    (like, node_type, limit),
                )
            else:
                cur.execute(
                    "SELECT node_id, node_type, label FROM nodes WHERE lower(label) LIKE ? LIMIT ?", (like, limit)
                )
            rows = cur.fetchall()
            results = [{"node_id": r[0], "node_type": r[1], "label": r[2]} for r in rows]
            return {"query": query, "count": len(results), "results": results}
        except Exception as e:
            return {"error": str(e)}

    def delete_node(self, node_id: str) -> Dict:
        """Removes the node and every edge touching it. Does NOT touch
        whatever record in episodic_memory.py/semantic_memory.py/etc.
        owns this node_id - that's memory_consolidator.py's call to
        make, this just keeps the graph consistent once it does."""
        try:
            with self._write_lock:
                self._conn.execute("DELETE FROM nodes WHERE node_id = ?", (node_id,))
                self._conn.execute("DELETE FROM edges WHERE from_id = ? OR to_id = ?", (node_id, node_id))
                self._conn.commit()
            return {"success": True, "deleted": node_id}
        except Exception as e:
            return {"error": str(e)}

    # -- edges ---------------------------------------------------------------
    def add_edge(self, from_id: str, to_id: str, relation: str, weight: float = 1.0) -> Dict:
        """Directed, typed edge (e.g. "episodic:42" --occurred_at--> "place:home").
        Both endpoints should already exist via add_node(), but this
        doesn't enforce it - a dangling edge is harmless (just won't
        surface via get_node) and enforcing it would make every caller
        deal with ordering it doesn't need to care about."""
        try:
            with self._write_lock:
                self._conn.execute(
                    "INSERT INTO edges (from_id, to_id, relation, weight, created_at) VALUES (?, ?, ?, ?, ?)",
                    (from_id, to_id, relation, weight, time.time()),
                )
                self._conn.commit()
            return {"success": True, "from_id": from_id, "to_id": to_id, "relation": relation}
        except Exception as e:
            return {"error": str(e)}

    def neighbors(self, node_id: str, relation: Optional[str] = None, direction: str = "both") -> Dict:
        """direction: "out" (edges from node_id), "in" (edges to
        node_id), or "both"."""
        try:
            cur = self._conn.cursor()
            results: List[Dict] = []
            if direction in ("out", "both"):
                q = "SELECT to_id, relation, weight FROM edges WHERE from_id = ?"
                params = [node_id]
                if relation:
                    q += " AND relation = ?"
                    params.append(relation)
                cur.execute(q, params)
                results += [
                    {"node_id": r[0], "relation": r[1], "weight": r[2], "direction": "out"} for r in cur.fetchall()
                ]
            if direction in ("in", "both"):
                q = "SELECT from_id, relation, weight FROM edges WHERE to_id = ?"
                params = [node_id]
                if relation:
                    q += " AND relation = ?"
                    params.append(relation)
                cur.execute(q, params)
                results += [
                    {"node_id": r[0], "relation": r[1], "weight": r[2], "direction": "in"} for r in cur.fetchall()
                ]
            return {"node_id": node_id, "count": len(results), "neighbors": results}
        except Exception as e:
            return {"error": str(e)}

    def find_path(self, start_id: str, end_id: str, max_depth: int = 4) -> Dict:
        """Breadth-first shortest path over edges in either direction
        (the graph is small enough - personal-assistant scale, same
        assumption memory/vector_db/vector_store.py makes - that BFS in
        Python is plenty fast; no need for a real graph DB)."""
        try:
            if start_id == end_id:
                return {"found": True, "path": [start_id], "hops": 0}
            visited = {start_id}
            queue = deque([(start_id, [start_id])])
            while queue:
                current, path = queue.popleft()
                if len(path) - 1 >= max_depth:
                    continue
                nb = self.neighbors(current, direction="both")
                if "error" in nb:
                    continue
                for edge in nb["neighbors"]:
                    nxt = edge["node_id"]
                    if nxt in visited:
                        continue
                    new_path = path + [nxt]
                    if nxt == end_id:
                        return {"found": True, "path": new_path, "hops": len(new_path) - 1}
                    visited.add(nxt)
                    queue.append((nxt, new_path))
            return {"found": False, "path": [], "hops": None}
        except Exception as e:
            return {"error": str(e)}

    def stats(self) -> Dict:
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM nodes")
            node_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM edges")
            edge_count = cur.fetchone()[0]
            cur.execute("SELECT node_type, COUNT(*) FROM nodes GROUP BY node_type")
            by_type = {r[0]: r[1] for r in cur.fetchall()}
            return {"nodes": node_count, "edges": edge_count, "by_type": by_type}
        except Exception as e:
            return {"error": str(e)}


def get_memory_graph() -> MemoryGraph:
    """Process-wide singleton, same pattern as core.events.get_event_bus()
    and PHASE_17_1_FOUNDATION's get_unified_bus()."""
    global _graph
    with _lock:
        if _graph is None:
            _graph = MemoryGraph()
        return _graph
