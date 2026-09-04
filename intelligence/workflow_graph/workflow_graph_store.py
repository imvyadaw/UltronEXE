"""
Workflow Graph Store (P5 - Personal Workflow Graph & Automation Discovery)
============================================================================
Sqlite CRUD for a small typed graph (nodes = workflows/tools, edges =
relations like "uses" or "often_followed_by"). intelligence/skill_builder/
already detects repeating action n-grams (workflow_detector.py) and
generalizes their params (workflow_analyzer.py), but neither connects
separate detected patterns to each other - there's no structure that
says "workflow A's last step tends to precede workflow B's first
step". This store is that connective structure.

Storage: database/workflow_graph.db, tables graph_nodes / graph_edges.
"""

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "workflow_graph.db"

_instance: Optional["WorkflowGraphStore"] = None
_instance_lock = threading.Lock()


class WorkflowGraphStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT,
                label TEXT,
                source_ref TEXT,
                created_at REAL,
                UNIQUE(node_type, label)
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS graph_edges (
                id TEXT PRIMARY KEY,
                from_id TEXT,
                to_id TEXT,
                relation TEXT,
                weight REAL,
                created_at REAL,
                updated_at REAL,
                UNIQUE(from_id, to_id, relation)
            )""")
        self._conn.commit()

    def add_node(self, node_type: str, label: str, source_ref: str = "") -> Dict:
        existing = self.find_node(node_type, label)
        if existing:
            return existing
        node_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO graph_nodes (id, node_type, label, source_ref, created_at) VALUES (?, ?, ?, ?, ?)",
                (node_id, node_type, label, source_ref, time.time()),
            )
            self._conn.commit()
        return self.get_node(node_id)

    def find_node(self, node_type: str, label: str) -> Optional[Dict]:
        row = self._conn.execute(
            "SELECT * FROM graph_nodes WHERE node_type = ? AND label = ?", (node_type, label)
        ).fetchone()
        return self._node_to_dict(row) if row else None

    def get_node(self, node_id: str) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM graph_nodes WHERE id = ?", (node_id,)).fetchone()
        return self._node_to_dict(row) if row else None

    def add_edge(self, from_id: str, to_id: str, relation: str, weight: float = 1.0) -> Dict:
        now = time.time()
        with self._lock:
            existing = self._conn.execute(
                "SELECT id, weight FROM graph_edges WHERE from_id = ? AND to_id = ? AND relation = ?",
                (from_id, to_id, relation),
            ).fetchone()
            if existing:
                edge_id, cur_weight = existing
                self._conn.execute(
                    "UPDATE graph_edges SET weight = ?, updated_at = ? WHERE id = ?",
                    (cur_weight + weight, now, edge_id),
                )
            else:
                edge_id = str(uuid.uuid4())
                self._conn.execute(
                    """INSERT INTO graph_edges (id, from_id, to_id, relation, weight, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (edge_id, from_id, to_id, relation, weight, now, now),
                )
            self._conn.commit()
        return self.get_edge(edge_id)

    def get_edge(self, edge_id: str) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM graph_edges WHERE id = ?", (edge_id,)).fetchone()
        return self._edge_to_dict(row) if row else None

    def get_edges_from(self, node_id: str) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM graph_edges WHERE from_id = ? ORDER BY weight DESC", (node_id,)
        ).fetchall()
        return [self._edge_to_dict(r) for r in rows]

    def get_edges_to(self, node_id: str) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM graph_edges WHERE to_id = ? ORDER BY weight DESC", (node_id,)
        ).fetchall()
        return [self._edge_to_dict(r) for r in rows]

    def get_all_nodes(self) -> List[Dict]:
        rows = self._conn.execute("SELECT * FROM graph_nodes").fetchall()
        return [self._node_to_dict(r) for r in rows]

    def get_all_edges(self, min_weight: float = 0.0) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM graph_edges WHERE weight >= ? ORDER BY weight DESC", (min_weight,)
        ).fetchall()
        return [self._edge_to_dict(r) for r in rows]

    @staticmethod
    def _node_to_dict(row) -> Dict:
        return {"id": row[0], "node_type": row[1], "label": row[2], "source_ref": row[3], "created_at": row[4]}

    @staticmethod
    def _edge_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "from_id": row[1],
            "to_id": row[2],
            "relation": row[3],
            "weight": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }


def get_workflow_graph_store() -> WorkflowGraphStore:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WorkflowGraphStore()
    return _instance
