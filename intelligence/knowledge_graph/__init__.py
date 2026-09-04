"""
Knowledge Graph (Phase 19.7)
=============================
Builds a living graph of people, projects, orgs, tools, and topics
out of what ULTRON actually observes in text - conversation turns,
notes, action params - and answers relationship questions back out
of it ("who's on this project", "how are X and Y connected", "what's
been active lately"). All backed by a shared database at
database/knowledge_graph.db:

    entity_extractor.py     - heuristically finds candidate entities
                               (people/projects/orgs/tools/dates) in text
    relation_mapper.py      - decides how co-occurring entities relate,
                               falling back to generic co-mention
    graph_store.py          - persists nodes/edges, tracks mention and
                               occurrence counts
    graph_query.py          - neighbor lookups, shortest-path search,
                               free-text search, centrality ranking
    people_graph.py         - person-shaped view + convenience linking
    project_graph.py        - project-shaped view + convenience linking
    temporal_graph.py       - chronological event log for timelines and
                               "what's active lately" queries
    knowledge_graph_engine.py - single entry point tying all of the
                               above together

Usage:
    from intelligence.knowledge_graph import get_knowledge_graph_engine
    kg = get_knowledge_graph_engine()

    # feed it text - it extracts entities, links them, logs the event
    result = kg.ingest("Vishal is working with Rohan on Phase 19.7 of Ultron.")

    # ask questions back
    kg.neighbors("ultron")
    kg.path("vishal", "rohan")
    kg.person("vishal")
    kg.project("ultron")
    kg.recent_activity(days=7)

Each sub-module also exposes its own get_x() singleton and can be
used directly without going through the top-level engine.

Purely additive - nothing in Phase 1-19.6 imports from here.
"""

from intelligence.knowledge_graph.entity_extractor import EntityExtractor, get_entity_extractor
from intelligence.knowledge_graph.relation_mapper import RelationMapper, get_relation_mapper
from intelligence.knowledge_graph.graph_store import GraphStore, get_graph_store
from intelligence.knowledge_graph.graph_query import GraphQuery, get_graph_query
from intelligence.knowledge_graph.people_graph import PeopleGraph, get_people_graph
from intelligence.knowledge_graph.project_graph import ProjectGraph, get_project_graph
from intelligence.knowledge_graph.temporal_graph import TemporalGraph, get_temporal_graph
from intelligence.knowledge_graph.knowledge_graph_engine import KnowledgeGraphEngine, get_knowledge_graph_engine

__all__ = [
    "KnowledgeGraphEngine",
    "get_knowledge_graph_engine",
    "EntityExtractor",
    "get_entity_extractor",
    "RelationMapper",
    "get_relation_mapper",
    "GraphStore",
    "get_graph_store",
    "GraphQuery",
    "get_graph_query",
    "PeopleGraph",
    "get_people_graph",
    "ProjectGraph",
    "get_project_graph",
    "TemporalGraph",
    "get_temporal_graph",
]
