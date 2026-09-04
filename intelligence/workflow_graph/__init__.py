"""
Personal Workflow Graph & Automation Discovery (P5)
====================================================
Turns detected repeating action patterns
(intelligence/skill_builder/workflow_detector.py) into a navigable
graph of workflows/tools/sequence edges, and mines it for chains
worth suggesting as a single automation - structure and discovery
that workflow_detector.py itself doesn't provide.

    workflow_graph_store.py  - sqlite CRUD for graph_nodes / graph_edges
    workflow_graph_engine.py - register/link/import + automation discovery

Usage:
    from intelligence.workflow_graph import get_workflow_graph_engine
    wge = get_workflow_graph_engine()
    wge.discover_automation_opportunities()

Purely additive - intelligence/skill_builder/workflow_detector.py and
core/workflow_engine.py are unmodified; this only reads the former
best-effort.
"""

from intelligence.workflow_graph.workflow_graph_store import WorkflowGraphStore, get_workflow_graph_store
from intelligence.workflow_graph.workflow_graph_engine import WorkflowGraphEngine, get_workflow_graph_engine

__all__ = ["WorkflowGraphStore", "get_workflow_graph_store", "WorkflowGraphEngine", "get_workflow_graph_engine"]
