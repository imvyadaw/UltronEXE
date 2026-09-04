"""
People Graph (Phase 19.7 - Knowledge Graph)
==================================================
A person-shaped window onto the same graph graph_store.py persists -
nothing here is a separate graph. Where graph_query.py answers
generic "what's connected to X" questions, this module answers the
specific questions that actually come up about people: who do we
know, who's connected to whom, what projects has this person been
tied to, who's been most active lately. Building a "person" through
this module (link_to_project() etc.) is just a thin, intent-labeled
wrapper over graph_store.py's upsert_node()/upsert_edge() - it exists
so callers don't have to remember type="person" and the right
relation_type string every time.
"""

import threading
from typing import Dict, List, Optional

from intelligence.knowledge_graph.graph_store import get_graph_store
from intelligence.knowledge_graph.graph_query import get_graph_query

_instance: Optional["PeopleGraph"] = None
_instance_lock = threading.Lock()

PERSON_TYPE = "person"


class PeopleGraph:
    """Person-centric convenience layer over graph_store.py / graph_query.py."""

    def __init__(self):
        self._store = get_graph_store()
        self._query = get_graph_query()

    def list_people(self, limit: int = 50) -> List[Dict]:
        return self._store.list_nodes(type=PERSON_TYPE, limit=limit)

    def get_person(self, name: str) -> Optional[Dict]:
        node = self._store.find_node(name, type=PERSON_TYPE)
        if node is None:
            return None
        neighbors = self._query.get_neighbors(name, type=PERSON_TYPE)
        projects = [n for n in neighbors if n["node"]["type"] == "project"]
        people = [n for n in neighbors if n["node"]["type"] == PERSON_TYPE]
        orgs = [n for n in neighbors if n["node"]["type"] == "org"]
        return {
            "node": node,
            "projects": projects,
            "related_people": people,
            "organizations": orgs,
            "total_connections": len(neighbors),
        }

    def most_mentioned_people(self, limit: int = 10) -> List[Dict]:
        return self.list_people(limit=limit)

    def link_people(self, name_a: str, name_b: str, relation_type: str = "knows") -> Dict:
        """Convenience wrapper: ensure both are person nodes and link
        them, e.g. after the engine notices two people mentioned
        together with no clearer relation from relation_mapper.py."""
        node_a = self._store.upsert_node(name_a.lower(), PERSON_TYPE, display_name=name_a)
        node_b = self._store.upsert_node(name_b.lower(), PERSON_TYPE, display_name=name_b)
        return self._store.upsert_edge(node_a["node_id"], node_b["node_id"], relation_type)

    def link_to_project(self, person_name: str, project_name: str, relation_type: str = "works_on") -> Dict:
        person = self._store.upsert_node(person_name.lower(), PERSON_TYPE, display_name=person_name)
        project = self._store.upsert_node(project_name.lower(), "project", display_name=project_name)
        return self._store.upsert_edge(person["node_id"], project["node_id"], relation_type)


def get_people_graph() -> PeopleGraph:
    """Process-wide PeopleGraph singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = PeopleGraph()
    return _instance
