"""
Workflow Analyzer (Phase 19.6 - Skill Builder)
==================================================
Turns one or more observed instances of the same action sequence
into a generalized template: a parameter that had the same value in
every instance becomes a fixed default; a parameter that varied
becomes a {{placeholder}} the skill will need filled in at run time.
Works whether it's handed a single explicit recording (one instance)
or several matched occurrences of a workflow_detector.py pattern
pulled from history (many instances - the more there are, the more
confidently constant-vs-variable can be told apart). This module
only generalizes - it doesn't decide whether to keep the result
(skill_generator.py's job) or persist it (skill_store.py's job).
"""

import threading
from typing import Dict, List, Optional

_instance: Optional["WorkflowAnalyzer"] = None
_instance_lock = threading.Lock()


class WorkflowAnalyzer:
    """occurrences (list of same-length, same-sequence step-lists) ->
    a generalized step template plus metadata for skill_generator.py."""

    def analyze(self, occurrences: List[List[Dict]]) -> Dict:
        """occurrences: e.g.
            [[{"action_name": "open_file", "params": {...}}, ...], [...], ...]
        - every inner list must be the same length and, position for
        position, the same action_name (that's what makes them
        "occurrences of the same workflow" rather than unrelated
        sequences that happen to be the same length)."""
        occurrences = [o for o in occurrences if o]
        if not occurrences:
            return {"is_generalizable": False, "reason": "no_occurrences", "steps": [], "sample_count": 0}

        length = len(occurrences[0])
        if length < 2:
            return {"is_generalizable": False, "reason": "too_short", "steps": [], "sample_count": len(occurrences)}
        if any(len(o) != length for o in occurrences):
            return {
                "is_generalizable": False,
                "reason": "inconsistent_length",
                "steps": [],
                "sample_count": len(occurrences),
            }
        for pos in range(length):
            names = {o[pos]["action_name"] for o in occurrences}
            if len(names) != 1:
                return {
                    "is_generalizable": False,
                    "reason": "inconsistent_sequence",
                    "steps": [],
                    "sample_count": len(occurrences),
                }

        generalized_steps = []
        variable_count = 0
        for pos in range(length):
            action_name = occurrences[0][pos]["action_name"]
            all_keys = set()
            for occurrence in occurrences:
                all_keys.update((occurrence[pos].get("params") or {}).keys())

            params = {}
            for key in sorted(all_keys):
                values = [(occurrence[pos].get("params") or {}).get(key) for occurrence in occurrences]
                if values[0] is not None and all(v == values[0] for v in values):
                    params[key] = values[0]
                else:
                    params[key] = "{{" + key + "}}"
                    variable_count += 1
            generalized_steps.append({"action_name": action_name, "params": params})

        action_sequence = [s["action_name"] for s in generalized_steps]
        return {
            "is_generalizable": True,
            "reason": "ok",
            "steps": generalized_steps,
            "action_sequence": action_sequence,
            "sample_count": len(occurrences),
            "variable_param_count": variable_count,
            # more repeats seen -> more confident the fixed/variable split is real
            "confidence": min(1.0, len(occurrences) / 5.0),
        }


def get_workflow_analyzer() -> WorkflowAnalyzer:
    """Process-wide WorkflowAnalyzer singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WorkflowAnalyzer()
    return _instance
