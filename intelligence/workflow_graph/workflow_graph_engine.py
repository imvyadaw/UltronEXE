"""
Workflow Graph Engine (P5 - Personal Workflow Graph & Automation Discovery)
=============================================================================
Turns Ultron's already-detected repeating action patterns
(intelligence/skill_builder/workflow_detector.py's get_candidates())
into an actual navigable graph - workflow nodes, the tool nodes each
one uses, and step-sequence edges between tools within a pattern -
then mines that graph for chains worth suggesting as a single
automation (e.g. "workflow A's last tool is followed by workflow B's
first tool often enough that chaining them into one macro would save
steps").

workflow_detector.py only ever answers "is this n-gram repeating";
it has no notion of *relationships between* separate patterns, and
core/workflow_engine.py executes a workflow once it exists but has no
discovery step. This engine is the missing structure + discovery
layer between the two - it reads workflow_detector.py best-effort
(never breaks if it's absent) and never modifies it.

Storage: intelligence/workflow_graph/workflow_graph_store.py
(database/workflow_graph.db).
"""

import time
from typing import Dict, List, Optional

from intelligence.workflow_graph.workflow_graph_store import get_workflow_graph_store

AUTOMATION_MIN_WEIGHT = 2.0


class WorkflowGraphEngine:
    def __init__(self):
        self._store = get_workflow_graph_store()

    # -- manual registration ----------------------------------------------
    def register_workflow(self, name: str, tools_used: List[str], source: str = "manual") -> Dict:
        wf_node = self._store.add_node("workflow", name, source)
        for i, tool in enumerate(tools_used):
            tool_node = self._store.add_node("tool", tool, source)
            self._store.add_edge(wf_node["id"], tool_node["id"], "uses", weight=1.0)
            if i > 0:
                prev_tool_node = self._store.add_node("tool", tools_used[i - 1], source)
                self._store.add_edge(prev_tool_node["id"], tool_node["id"], "step_after", weight=1.0)
        return wf_node

    def link_sequence(
        self, workflow_a: str, workflow_b: str, relation: str = "often_followed_by", weight: float = 1.0
    ) -> Dict:
        node_a = self._store.find_node("workflow", workflow_a) or self._store.add_node("workflow", workflow_a)
        node_b = self._store.find_node("workflow", workflow_b) or self._store.add_node("workflow", workflow_b)
        return self._store.add_edge(node_a["id"], node_b["id"], relation, weight)

    # -- best-effort import from skill_builder's detector -------------------
    def import_detected_patterns(self, min_occurrences: int = 2) -> Dict:
        patterns = self._best_effort_get_candidates(min_occurrences)
        if not patterns:
            return {"imported": 0, "reason": "no detected patterns available or workflow_detector not present"}
        imported = 0
        for pattern in patterns:
            actions = pattern.get("actions", [])
            if len(actions) < 2:
                continue
            name = f"pattern:{pattern.get('signature', '-'.join(actions[:3]))}"
            self.register_workflow(name, actions, source="skill_builder.workflow_detector")
            for i in range(len(actions) - 1):
                a = self._store.add_node("tool", actions[i], "skill_builder.workflow_detector")
                b = self._store.add_node("tool", actions[i + 1], "skill_builder.workflow_detector")
                self._store.add_edge(a["id"], b["id"], "step_after", weight=float(pattern.get("occurrence_count", 1)))
            imported += 1
        return {"imported": imported}

    # -- discovery ----------------------------------------------------------
    def discover_automation_opportunities(self, min_weight: float = AUTOMATION_MIN_WEIGHT) -> List[Dict]:
        self.import_detected_patterns()
        edges = self._store.get_all_edges(min_weight=min_weight)
        suggestions = []
        for edge in edges:
            if edge["relation"] not in ("step_after", "often_followed_by"):
                continue
            from_node = self._store.get_node(edge["from_id"])
            to_node = self._store.get_node(edge["to_id"])
            if not from_node or not to_node:
                continue
            suggestions.append(
                {
                    "from": from_node["label"],
                    "to": to_node["label"],
                    "relation": edge["relation"],
                    "weight": edge["weight"],
                    "suggestion": f"'{from_node['label']}' is reliably followed by '{to_node['label']}' "
                    f"({edge['weight']:.0f}x observed) - consider chaining into one automation.",
                }
            )
        suggestions.sort(key=lambda s: s["weight"], reverse=True)
        return suggestions

    def get_workflow_neighbors(self, name: str) -> Dict:
        node = self._store.find_node("workflow", name)
        if not node:
            return {"found": False}
        uses = [
            self._store.get_node(e["to_id"]) for e in self._store.get_edges_from(node["id"]) if e["relation"] == "uses"
        ]
        followed_by = [
            self._store.get_node(e["to_id"])
            for e in self._store.get_edges_from(node["id"])
            if e["relation"] == "often_followed_by"
        ]
        return {
            "found": True,
            "workflow": node,
            "uses_tools": [n["label"] for n in uses if n],
            "often_followed_by": [n["label"] for n in followed_by if n],
        }

    def get_graph_summary(self) -> Dict:
        nodes = self._store.get_all_nodes()
        edges = self._store.get_all_edges()
        return {
            "workflow_count": sum(1 for n in nodes if n["node_type"] == "workflow"),
            "tool_count": sum(1 for n in nodes if n["node_type"] == "tool"),
            "edge_count": len(edges),
            "top_edges": edges[:10],
            "checked_at": time.time(),
        }

    @staticmethod
    def _best_effort_get_candidates(min_occurrences: int) -> Optional[List[Dict]]:
        try:
            from intelligence.skill_builder.workflow_detector import get_workflow_detector

            return get_workflow_detector().get_candidates(min_occurrences=min_occurrences, limit=25)
        except Exception:
            return None


_instance: Optional[WorkflowGraphEngine] = None


def get_workflow_graph_engine() -> WorkflowGraphEngine:
    global _instance
    if _instance is None:
        _instance = WorkflowGraphEngine()
    return _instance
