"""
Project Graph (Phase 19.7 - Knowledge Graph)
==================================================
The project-shaped counterpart to people_graph.py, same idea: a
labeled window onto graph_store.py's graph rather than a separate
store. Answers "who's on this project", "what tools does it use",
"what other projects relate to it", and "what's most active lately" -
the questions that actually come up about projects, phrased without
the caller needing to know type="project" or the exact relation_type
strings graph_store.py expects.
"""

import threading
from typing import Dict, List, Optional

from intelligence.knowledge_graph.graph_store import get_graph_store
from intelligence.knowledge_graph.graph_query import get_graph_query

_instance: Optional["ProjectGraph"] = None
_instance_lock = threading.Lock()

PROJECT_TYPE = "project"


class ProjectGraph:
    """Project-centric convenience layer over graph_store.py / graph_query.py."""

    def __init__(self):
        self._store = get_graph_store()
        self._query = get_graph_query()

    def list_projects(self, limit: int = 50) -> List[Dict]:
        return self._store.list_nodes(type=PROJECT_TYPE, limit=limit)

    def get_project(self, name: str) -> Optional[Dict]:
        node = self._store.find_node(name, type=PROJECT_TYPE)
        if node is None:
            return None
        neighbors = self._query.get_neighbors(name, type=PROJECT_TYPE)
        team = [n for n in neighbors if n["node"]["type"] == "person"]
        tools = [n for n in neighbors if n["node"]["type"] == "tool"]
        related_projects = [n for n in neighbors if n["node"]["type"] == PROJECT_TYPE]
        return {
            "node": node,
            "team": team,
            "tools": tools,
            "related_projects": related_projects,
            "total_connections": len(neighbors),
        }

    def most_active_projects(self, limit: int = 10) -> List[Dict]:
        """Ranked by mention_count, which last_seen_at-aware
        temporal_graph.py's recent_activity() complements with an
        actual recency window when "active" needs to mean "lately"
        rather than "ever"."""
        return self.list_projects(limit=limit)

    def link_tool(self, project_name: str, tool_name: str, relation_type: str = "uses") -> Dict:
        project = self._store.upsert_node(project_name.lower(), PROJECT_TYPE, display_name=project_name)
        tool = self._store.upsert_node(tool_name.lower(), "tool", display_name=tool_name)
        return self._store.upsert_edge(project["node_id"], tool["node_id"], relation_type)

    def link_projects(self, project_a: str, project_b: str, relation_type: str = "related_to") -> Dict:
        node_a = self._store.upsert_node(project_a.lower(), PROJECT_TYPE, display_name=project_a)
        node_b = self._store.upsert_node(project_b.lower(), PROJECT_TYPE, display_name=project_b)
        return self._store.upsert_edge(node_a["node_id"], node_b["node_id"], relation_type)


def get_project_graph() -> ProjectGraph:
    """Process-wide ProjectGraph singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ProjectGraph()
    return _instance
