"""
Knowledge Graph Engine (Phase 19.7 - Knowledge Graph)
=====================================================
Single entry point for the knowledge_graph/ package: turn raw text
ULTRON observes (a conversation turn, a note, an action's params)
into graph nodes and edges, and answer questions back out of it.
Ties together:

    entity_extractor.py  - finds candidate entities in text
    relation_mapper.py    - decides how co-occurring entities relate
    graph_store.py        - persists nodes/edges, tracks mention/
                             occurrence counts
    graph_query.py         - neighbor lookups, shortest-path search,
                             free-text search
    people_graph.py        - person-shaped view + convenience linking
    project_graph.py       - project-shaped view + convenience linking
    temporal_graph.py      - chronological event log on top of the
                             graph's own last-touched timestamps

One way in: ingest(text, hints=...) extracts entities, upserts them
as nodes, maps and upserts relations as edges, and logs a temporal
event for each - mirroring Phase 19.6's skill_builder_engine.py
pattern of a thin orchestrator over otherwise-independent sub-modules
that each still work fine called directly.

Storage: database/knowledge_graph.db, table graph_runs (this
module's own table; the other seven sub-modules each keep their own
tables in the same database file).

Purely additive - nothing in Phase 1-19.6 imports from here.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from intelligence.knowledge_graph.entity_extractor import get_entity_extractor
from intelligence.knowledge_graph.relation_mapper import get_relation_mapper
from intelligence.knowledge_graph.graph_store import get_graph_store
from intelligence.knowledge_graph.graph_query import get_graph_query
from intelligence.knowledge_graph.people_graph import get_people_graph
from intelligence.knowledge_graph.project_graph import get_project_graph
from intelligence.knowledge_graph.temporal_graph import get_temporal_graph

logger = get_logger("ultron.knowledge_graph_engine")

DB_PATH = Path(__file__).resolve().parent.parent.parent / "database" / "knowledge_graph.db"

_instance: Optional["KnowledgeGraphEngine"] = None
_instance_lock = threading.Lock()


class KnowledgeGraphEngine:
    """Orchestrates entity_extractor / relation_mapper / graph_store /
    graph_query / people_graph / project_graph / temporal_graph into a
    single ingest() pipeline, plus read-through passthroughs for
    everything else, and logs every ingest attempt."""

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("""CREATE TABLE IF NOT EXISTS graph_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                outcome TEXT,
                entities_found INTEGER,
                relations_found INTEGER,
                detail TEXT,
                timestamp REAL
            )""")
        self._conn.commit()

        self._extractor = get_entity_extractor()
        self._mapper = get_relation_mapper()
        self._store = get_graph_store()
        self._query = get_graph_query()
        self._people = get_people_graph()
        self._projects = get_project_graph()
        self._temporal = get_temporal_graph()

    # ---- ingest -------------------------------------------------------------

    def ingest(self, text: str, source: str = "conversation", hints: Optional[Dict[str, str]] = None) -> Dict:
        """Extract entities from `text`, upsert them as nodes, map and
        upsert relations between co-occurring ones as edges, and log a
        temporal event for each node/edge touched. `hints` forces a
        specific name to a specific type (e.g. {"vishal": "person"})
        instead of relying on entity_extractor.py's guess."""
        entities = self._extractor.extract(text, hints=hints)
        if not entities:
            run_id = self._log_run(source, "no_entities", 0, 0, "nothing extracted")
            return {"outcome": "no_entities", "entities": [], "relations": [], "run_id": run_id}

        name_to_node: Dict[str, Dict] = {}
        for entity in entities:
            node = self._store.upsert_node(entity["name"], entity["type"], display_name=entity["display_name"])
            name_to_node[entity["name"]] = node
            self._temporal.log_event(
                "node_touched",
                node_id=node["node_id"],
                node_name=node["name"],
                detail={"type": node["type"], "source": source},
            )

        relations = self._mapper.map_relations(text, entities)
        created_edges = []
        for relation in relations:
            source_node = name_to_node.get(relation["source"])
            target_node = name_to_node.get(relation["target"])
            if source_node is None or target_node is None:
                continue
            edge = self._store.upsert_edge(
                source_node["node_id"],
                target_node["node_id"],
                relation["relation_type"],
                attributes={"context": relation["context"]},
            )
            created_edges.append(edge)
            self._temporal.log_event(
                "edge_touched",
                edge_id=edge["edge_id"],
                node_name=source_node["name"],
                detail={"relation_type": relation["relation_type"], "target": target_node["name"]},
            )

        run_id = self._log_run(
            source,
            "ingested",
            len(entities),
            len(created_edges),
            f"{len(entities)} entities, {len(created_edges)} relations",
        )
        logger.info(f"ingested '{source}': {len(entities)} entities, {len(created_edges)} relations")
        return {
            "outcome": "ingested",
            "entities": list(name_to_node.values()),
            "relations": created_edges,
            "run_id": run_id,
        }

    # ---- read passthroughs ---------------------------------------------------

    def neighbors(self, name: str, type: Optional[str] = None, limit: int = 20) -> List[Dict]:
        return self._query.get_neighbors(name, type=type, limit=limit)

    def path(self, name_a: str, name_b: str, max_depth: int = 4) -> Optional[List[Dict]]:
        return self._query.find_path(name_a, name_b, max_depth=max_depth)

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        return self._query.search(query, limit=limit)

    def most_connected(self, type: Optional[str] = None, limit: int = 10) -> List[Dict]:
        return self._query.most_connected(type=type, limit=limit)

    def person(self, name: str) -> Optional[Dict]:
        return self._people.get_person(name)

    def project(self, name: str) -> Optional[Dict]:
        return self._projects.get_project(name)

    def timeline(self, name: str, limit: int = 50) -> List[Dict]:
        return self._temporal.get_timeline(name, limit=limit)

    def recent_activity(self, days: int = 7, limit: int = 50) -> List[Dict]:
        return self._temporal.recent_activity(days=days, limit=limit)

    def get_stats(self) -> Dict:
        return {
            "node_count": self._store.node_count(),
            "edge_count": self._store.edge_count(),
            "people_count": self._store.node_count(type="person"),
            "project_count": self._store.node_count(type="project"),
        }

    # ---- bookkeeping ---------------------------------------------------------

    def _log_run(self, source: str, outcome: str, entities_found: int, relations_found: int, detail: str) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO graph_runs (source, outcome, entities_found, relations_found, detail, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source, outcome, entities_found, relations_found, detail, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_history(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, source, outcome, entities_found, relations_found, detail, timestamp
                   FROM graph_runs ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "source": r[1],
                "outcome": r[2],
                "entities_found": r[3],
                "relations_found": r[4],
                "detail": r[5],
                "timestamp": r[6],
            }
            for r in rows
        ]


def get_knowledge_graph_engine() -> KnowledgeGraphEngine:
    """Process-wide KnowledgeGraphEngine singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = KnowledgeGraphEngine()
    return _instance
