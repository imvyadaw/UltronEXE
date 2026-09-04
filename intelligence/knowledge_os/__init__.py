"""
Knowledge OS (P3 - Unified Personal Knowledge OS)
==================================================
Single front door over Ultron's otherwise-scattered knowledge:
knowledge_graph, semantic_memory, and its own source-tagged fact
ledger for things explicitly told to it.

    knowledge_store.py    - sqlite CRUD for the OS's own facts table
    knowledge_os_engine.py - unified read/search + best-effort
                              cross-subsystem enrichment + staleness

Usage:
    from intelligence.knowledge_os import get_knowledge_os
    kos = get_knowledge_os()
    kos.remember_fact("project x", "deadline is nov 12", source="user")
    kos.get_unified_view("project x")

Purely additive - nothing in knowledge_graph_engine.py or
semantic_memory.py is modified; this only reads from them best-effort.
"""

from intelligence.knowledge_os.knowledge_store import KnowledgeStore, get_knowledge_store
from intelligence.knowledge_os.knowledge_os_engine import KnowledgeOS, get_knowledge_os

__all__ = ["KnowledgeStore", "get_knowledge_store", "KnowledgeOS", "get_knowledge_os"]
