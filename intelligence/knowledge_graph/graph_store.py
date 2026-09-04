"""
Graph Store (Phase 19.7 - Knowledge Graph)
==================================================
Persistent home for the graph itself: nodes (people, projects, orgs,
tools, places, dates, topics...) and the weighted edges between them.
Purely a record-keeper, same spirit as skill_builder/skill_store.py -
it doesn't decide what's an entity (entity_extractor.py) or how two
entities relate (relation_mapper.py), it just upserts and answers
"what do we know about this node/edge". Every upsert bumps
mention_count / occurrence_count and last_seen_at rather than
inserting duplicates, so the graph naturally reflects "what keeps
coming up" without any separate decay/scoring pass.

Storage: database/knowledge_graph.db, tables kg_nodes and kg_edges.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "knowledge_graph.db"

_instance: Optional["GraphStore"] = None
_instance_lock = threading.Lock()


class GraphStore:
    """CRUD + mention/occurrence tracking for graph nodes and edges."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS kg_nodes (
                node_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                display_name TEXT,
                type TEXT,
                attributes_json TEXT,
                mention_count INTEGER DEFAULT 1,
                first_seen_at REAL,
                last_seen_at REAL,
                UNIQUE(name, type)
            )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS kg_edges (
                edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                target_id INTEGER,
                relation_type TEXT,
                occurrence_count INTEGER DEFAULT 1,
                weight REAL DEFAULT 1.0,
                attributes_json TEXT,
                first_seen_at REAL,
                last_seen_at REAL,
                UNIQUE(source_id, target_id, relation_type)
            )""")
        self._conn.commit()

    # ---- nodes -------------------------------------------------------------

    def upsert_node(
        self, name: str, type: str, display_name: Optional[str] = None, attributes: Optional[Dict] = None
    ) -> Dict:
        """Insert a new node or, if (name, type) already exists, bump
        its mention_count and last_seen_at. `name` should already be
        normalized (entity_extractor.py's job) - this layer treats it
        as an opaque key."""
        now = time.time()
        with self._lock:
            existing = self._conn.execute(
                "SELECT node_id FROM kg_nodes WHERE name = ? AND type = ?", (name, type)
            ).fetchone()
            if existing:
                node_id = existing[0]
                self._conn.execute(
                    """UPDATE kg_nodes SET mention_count = mention_count + 1,
                       last_seen_at = ?, display_name = COALESCE(?, display_name)
                       WHERE node_id = ?""",
                    (now, display_name, node_id),
                )
            else:
                cur = self._conn.execute(
                    """INSERT INTO kg_nodes
                       (name, display_name, type, attributes_json, mention_count, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (name, display_name or name, type, json.dumps(attributes or {}), now, now),
                )
                node_id = cur.lastrowid
            self._conn.commit()
        return self.get_node(node_id)

    def get_node(self, node_id: int) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT node_id, name, display_name, type, attributes_json,
                          mention_count, first_seen_at, last_seen_at
                   FROM kg_nodes WHERE node_id = ?""",
                (node_id,),
            ).fetchone()
        return self._row_to_node(row) if row else None

    def find_node(self, name: str, type: Optional[str] = None) -> Optional[Dict]:
        """Case-insensitive lookup by normalized name, optionally
        narrowed to a type. Most-mentioned match wins if the same
        name exists under more than one type."""
        with self._lock:
            if type:
                row = self._conn.execute(
                    "SELECT node_id FROM kg_nodes WHERE name = ? AND type = ?", (name.lower(), type)
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT node_id FROM kg_nodes WHERE name = ? ORDER BY mention_count DESC LIMIT 1",
                    (name.lower(),),
                ).fetchone()
        return self.get_node(row[0]) if row else None

    def list_nodes(self, type: Optional[str] = None, limit: int = 50) -> List[Dict]:
        with self._lock:
            if type:
                rows = self._conn.execute(
                    """SELECT node_id, name, display_name, type, attributes_json,
                              mention_count, first_seen_at, last_seen_at
                       FROM kg_nodes WHERE type = ? ORDER BY mention_count DESC LIMIT ?""",
                    (type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT node_id, name, display_name, type, attributes_json,
                              mention_count, first_seen_at, last_seen_at
                       FROM kg_nodes ORDER BY mention_count DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def search_nodes(self, query: str, limit: int = 10) -> List[Dict]:
        like = f"%{query.lower()}%"
        with self._lock:
            rows = self._conn.execute(
                """SELECT node_id, name, display_name, type, attributes_json,
                          mention_count, first_seen_at, last_seen_at
                   FROM kg_nodes WHERE name LIKE ? ORDER BY mention_count DESC LIMIT ?""",
                (like, limit),
            ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def delete_node(self, node_id: int) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM kg_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            self._conn.execute("DELETE FROM kg_nodes WHERE node_id = ?", (node_id,))
            self._conn.commit()
        return {"success": True, "node_id": node_id}

    # ---- edges -------------------------------------------------------------

    def upsert_edge(
        self, source_id: int, target_id: int, relation_type: str, weight: float = 1.0, attributes: Optional[Dict] = None
    ) -> Dict:
        """Insert a new edge or, if (source, target, relation_type)
        already exists, bump occurrence_count/weight and last_seen_at."""
        now = time.time()
        with self._lock:
            existing = self._conn.execute(
                """SELECT edge_id FROM kg_edges
                   WHERE source_id = ? AND target_id = ? AND relation_type = ?""",
                (source_id, target_id, relation_type),
            ).fetchone()
            if existing:
                edge_id = existing[0]
                self._conn.execute(
                    """UPDATE kg_edges SET occurrence_count = occurrence_count + 1,
                       weight = weight + ?, last_seen_at = ? WHERE edge_id = ?""",
                    (weight, now, edge_id),
                )
            else:
                cur = self._conn.execute(
                    """INSERT INTO kg_edges
                       (source_id, target_id, relation_type, occurrence_count, weight,
                        attributes_json, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, 1, ?, ?, ?, ?)""",
                    (source_id, target_id, relation_type, weight, json.dumps(attributes or {}), now, now),
                )
                edge_id = cur.lastrowid
            self._conn.commit()
        return self.get_edge(edge_id)

    def get_edge(self, edge_id: int) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT edge_id, source_id, target_id, relation_type, occurrence_count,
                          weight, attributes_json, first_seen_at, last_seen_at
                   FROM kg_edges WHERE edge_id = ?""",
                (edge_id,),
            ).fetchone()
        return self._row_to_edge(row) if row else None

    def get_edges_for_node(self, node_id: int, relation_type: Optional[str] = None) -> List[Dict]:
        """Every edge touching node_id in either direction."""
        with self._lock:
            if relation_type:
                rows = self._conn.execute(
                    """SELECT edge_id, source_id, target_id, relation_type, occurrence_count,
                              weight, attributes_json, first_seen_at, last_seen_at
                       FROM kg_edges WHERE (source_id = ? OR target_id = ?) AND relation_type = ?
                       ORDER BY weight DESC""",
                    (node_id, node_id, relation_type),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT edge_id, source_id, target_id, relation_type, occurrence_count,
                              weight, attributes_json, first_seen_at, last_seen_at
                       FROM kg_edges WHERE source_id = ? OR target_id = ?
                       ORDER BY weight DESC""",
                    (node_id, node_id),
                ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def delete_edge(self, edge_id: int) -> Dict:
        with self._lock:
            self._conn.execute("DELETE FROM kg_edges WHERE edge_id = ?", (edge_id,))
            self._conn.commit()
        return {"success": True, "edge_id": edge_id}

    # ---- stats -------------------------------------------------------------

    def node_count(self, type: Optional[str] = None) -> int:
        with self._lock:
            if type:
                row = self._conn.execute("SELECT COUNT(*) FROM kg_nodes WHERE type = ?", (type,)).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()
        return row[0] if row else 0

    def edge_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()
        return row[0] if row else 0

    @staticmethod
    def _row_to_node(row) -> Dict:
        node_id, name, display_name, type, attributes_json, mention_count, first_seen_at, last_seen_at = row
        try:
            attributes = json.loads(attributes_json) if attributes_json else {}
        except Exception:
            attributes = {}
        return {
            "node_id": node_id,
            "name": name,
            "display_name": display_name,
            "type": type,
            "attributes": attributes,
            "mention_count": mention_count,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
        }

    @staticmethod
    def _row_to_edge(row) -> Dict:
        (
            edge_id,
            source_id,
            target_id,
            relation_type,
            occurrence_count,
            weight,
            attributes_json,
            first_seen_at,
            last_seen_at,
        ) = row
        try:
            attributes = json.loads(attributes_json) if attributes_json else {}
        except Exception:
            attributes = {}
        return {
            "edge_id": edge_id,
            "source_id": source_id,
            "target_id": target_id,
            "relation_type": relation_type,
            "occurrence_count": occurrence_count,
            "weight": weight,
            "attributes": attributes,
            "first_seen_at": first_seen_at,
            "last_seen_at": last_seen_at,
        }


def get_graph_store() -> GraphStore:
    """Process-wide GraphStore singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GraphStore()
    return _instance
