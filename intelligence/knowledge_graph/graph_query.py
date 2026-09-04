"""
Graph Query (Phase 19.7 - Knowledge Graph)
==================================================
Read-only question-answering over what graph_store.py has persisted:
"what's connected to X", "how are X and Y connected", "search for
X", "what's most talked about". Nothing here writes to the graph -
that's graph_store.py's job via knowledge_graph_engine.py's ingest
pipeline. Kept separate from graph_store.py itself so the store stays
a plain CRUD layer while the actual graph algorithms (BFS path
search, neighbor ranking) live in one place.
"""

import threading
from collections import deque
from typing import Dict, List, Optional

from intelligence.knowledge_graph.graph_store import get_graph_store

_instance: Optional["GraphQuery"] = None
_instance_lock = threading.Lock()


class GraphQuery:
    """Neighbor lookups, shortest-path search, and free-text search
    over the graph_store.py-backed graph."""

    def __init__(self):
        self._store = get_graph_store()

    def get_neighbors(
        self, name: str, type: Optional[str] = None, relation_type: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        node = self._store.find_node(name, type=type)
        if node is None:
            return []
        edges = self._store.get_edges_for_node(node["node_id"], relation_type=relation_type)
        neighbors = []
        for edge in edges[:limit]:
            other_id = edge["target_id"] if edge["source_id"] == node["node_id"] else edge["source_id"]
            other = self._store.get_node(other_id)
            if other is None:
                continue
            neighbors.append(
                {
                    "node": other,
                    "relation_type": edge["relation_type"],
                    "weight": edge["weight"],
                    "occurrence_count": edge["occurrence_count"],
                }
            )
        return neighbors

    def find_path(self, name_a: str, name_b: str, max_depth: int = 4) -> Optional[List[Dict]]:
        """Shortest path (BFS, unweighted) between two entities by
        name, as an ordered list of {"node", "relation_type"} hops
        starting from name_a. None if no path within max_depth."""
        start = self._store.find_node(name_a)
        end = self._store.find_node(name_b)
        if start is None or end is None:
            return None
        if start["node_id"] == end["node_id"]:
            return []

        visited = {start["node_id"]}
        queue = deque([(start["node_id"], [])])
        while queue:
            node_id, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for edge in self._store.get_edges_for_node(node_id):
                other_id = edge["target_id"] if edge["source_id"] == node_id else edge["source_id"]
                if other_id in visited:
                    continue
                other = self._store.get_node(other_id)
                if other is None:
                    continue
                new_path = path + [{"node": other, "relation_type": edge["relation_type"]}]
                if other_id == end["node_id"]:
                    return new_path
                visited.add(other_id)
                queue.append((other_id, new_path))
        return None

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        return self._store.search_nodes(query, limit=limit)

    def most_connected(self, type: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Nodes ranked by total edge weight touching them - a proxy
        for "how central is this entity to the graph", not just how
        often it was mentioned."""
        candidates = self._store.list_nodes(type=type, limit=limit * 5)
        scored = []
        for node in candidates:
            edges = self._store.get_edges_for_node(node["node_id"])
            score = sum(e["weight"] for e in edges)
            scored.append({"node": node, "connection_score": score, "edge_count": len(edges)})
        scored.sort(key=lambda x: x["connection_score"], reverse=True)
        return scored[:limit]

    def get_node_detail(self, name: str, type: Optional[str] = None) -> Optional[Dict]:
        node = self._store.find_node(name, type=type)
        if node is None:
            return None
        neighbors = self.get_neighbors(name, type=type)
        return {"node": node, "neighbors": neighbors, "neighbor_count": len(neighbors)}


def get_graph_query() -> GraphQuery:
    """Process-wide GraphQuery singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = GraphQuery()
    return _instance
