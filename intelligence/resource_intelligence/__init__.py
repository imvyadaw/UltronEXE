"""
Resource-Aware Intelligence Engine (P3)
========================================
Recommends how a task should actually be executed (full local run,
lighter path, deferred, or cloud-offloaded) based on current system
load plus that task type's own empirical cost history - a decision
layer that sits above monitoring/resource_monitor.py and complements
(does not replace) intelligence/predictive_preparation/resource_optimizer.py.

    resource_store.py        - sqlite CRUD for per-task-type cost history
    resource_aware_engine.py - load + history -> execution tier recommendation

Usage:
    from intelligence.resource_intelligence import get_resource_aware_engine
    rae = get_resource_aware_engine()
    rae.recommend_execution_tier("research_topic", estimated_cost="high")
    rae.track_task_execution("research_topic", duration_ms=4200, ...)

Purely additive - monitoring/resource_monitor.py and
resource_optimizer.py are unmodified.
"""

from intelligence.resource_intelligence.resource_store import ResourceStore, get_resource_store
from intelligence.resource_intelligence.resource_aware_engine import ResourceAwareEngine, get_resource_aware_engine

__all__ = ["ResourceStore", "get_resource_store", "ResourceAwareEngine", "get_resource_aware_engine"]
