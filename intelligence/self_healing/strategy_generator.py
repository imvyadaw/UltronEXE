"""
Strategy Generator (Phase 19.5 - Self Healing)
==================================================
Turns a failure_diagnoser.py diagnosis into an ordered list of
candidate recovery strategies to try. Fully offline and rule-based -
a small category -> catalog table covers the common failure shapes
(timeout, missing_resource, permission, network,
resource_exhausted, verification_failed, unknown), and whichever
strategy healing_memory.py remembers as having actually worked for
this exact failure signature before gets moved to the front of the
list. This module only proposes strategies in order - it never runs
them; that's self_healing_engine.py's job.
"""

import threading
from typing import Dict, List, Optional

from intelligence.self_healing.healing_memory import get_healing_memory

_instance: Optional["StrategyGenerator"] = None
_instance_lock = threading.Lock()

# category -> ordered catalog of {"name", "description"} strategies.
_CATALOG = {
    "timeout": [
        {"name": "retry_with_backoff", "description": "Wait and retry with increasing delay"},
        {"name": "increase_timeout", "description": "Retry once more with a longer timeout budget"},
        {"name": "escalate_to_user", "description": "Surface the repeated timeout to the user"},
    ],
    "missing_resource": [
        {"name": "create_missing_path", "description": "Create the missing file/directory and retry"},
        {"name": "use_fallback_path", "description": "Retry against a known alternate location"},
        {"name": "escalate_to_user", "description": "Ask the user where the resource actually is"},
    ],
    "permission": [
        {"name": "retry_with_elevated_permission", "description": "Retry the action with elevated permissions"},
        {"name": "use_alternate_location", "description": "Write/read from a location the process can access"},
        {"name": "escalate_to_user", "description": "Ask the user to grant the needed permission"},
    ],
    "network": [
        {"name": "retry_after_delay", "description": "Wait for the network blip to pass and retry"},
        {"name": "switch_to_offline_mode", "description": "Fall back to cached/offline behavior"},
        {"name": "escalate_to_user", "description": "Report the persistent network failure"},
    ],
    "resource_exhausted": [
        {"name": "free_resources_and_retry", "description": "Release memory/handles/disk space, then retry"},
        {"name": "retry_after_delay", "description": "Back off and retry once load/rate-limit clears"},
        {"name": "escalate_to_user", "description": "Report that the system is out of a needed resource"},
    ],
    "no_visible_effect": [
        {"name": "retry_once", "description": "Retry the action once in case it silently no-op'd"},
        {"name": "use_fallback_path", "description": "Try an alternate way of performing the action"},
        {"name": "escalate_to_user", "description": "Report that the action doesn't appear to do anything"},
    ],
    "unexpected_result": [
        {"name": "retry_once", "description": "Retry once in case the bad result was transient"},
        {"name": "use_fallback_path", "description": "Try an alternate approach that produces the expected result"},
        {"name": "escalate_to_user", "description": "Report the mismatch between expected and actual result"},
    ],
    "verification_failed": [
        {"name": "retry_once", "description": "Retry the action once before assuming it's broken"},
        {"name": "use_fallback_path", "description": "Try an alternate approach and re-verify"},
        {"name": "escalate_to_user", "description": "Report that verification keeps failing"},
    ],
    "unknown": [
        {"name": "retry_once", "description": "Retry once - many failures are transient"},
        {"name": "escalate_to_user", "description": "Surface the unclassified failure to the user"},
    ],
}


class StrategyGenerator:
    """diagnosis -> ordered list of candidate strategies, with any
    previously-successful strategy for this exact signature bumped to
    the front."""

    def __init__(self):
        self._memory = get_healing_memory()

    def generate(self, diagnosis: Dict) -> List[Dict]:
        category = diagnosis.get("category", "unknown")
        catalog = _CATALOG.get(category, _CATALOG["unknown"])
        strategies = [dict(s) for s in catalog]  # shallow copy, don't mutate the catalog

        remembered = self._memory.best_strategy_for(diagnosis.get("signature", ""))
        if remembered:
            name = remembered["strategy_name"]
            match = next((s for s in strategies if s["name"] == name), None)
            if match:
                strategies.remove(match)
            else:
                match = {"name": name, "description": "Previously successful fix for this exact failure"}
            match["proven"] = True
            match["success_count"] = remembered["success_count"]
            strategies.insert(0, match)

        return strategies


def get_strategy_generator() -> StrategyGenerator:
    """Process-wide StrategyGenerator singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = StrategyGenerator()
    return _instance
