"""
Skill Generator (Phase 19.6 - Skill Builder)
==================================================
Turns a workflow_analyzer.py analysis into a concrete, storable
skill definition: a name, a human-readable description, and the
generalized ordered steps (already carrying {{placeholder}}s for
whatever varied across instances). This module only builds the
definition in memory - it never persists it (skill_store.py's job)
or runs it (skill_builder_engine.py's job).
"""

import hashlib
import threading
import time
from typing import Dict, List, Optional

_instance: Optional["SkillGenerator"] = None
_instance_lock = threading.Lock()


class SkillGenerator:
    """analysis -> a {"name", "description", "steps", ...} skill
    definition ready for skill_store.py."""

    def generate(
        self, analysis: Dict, name: Optional[str] = None, description: Optional[str] = None, source: str = "recording"
    ) -> Dict:
        if not analysis.get("is_generalizable"):
            raise ValueError(f"analysis is not generalizable: {analysis.get('reason')}")

        steps = analysis["steps"]
        action_sequence = analysis.get("action_sequence") or [s["action_name"] for s in steps]

        return {
            "name": name or self.default_name(action_sequence),
            "description": description or self.default_description(action_sequence),
            "steps": steps,
            "action_sequence": action_sequence,
            "sample_count": analysis.get("sample_count", 1),
            "confidence": analysis.get("confidence", 0.2),
            "source": source,
            "generated_at": time.time(),
        }

    @staticmethod
    def default_name(action_sequence: List[str]) -> str:
        """Deterministic for a given action_sequence, so callers (the
        engine's duplicate check when building from a detected
        pattern) can predict a skill's name before generating it."""
        slug = "_then_".join(action_sequence[:4])
        if len(action_sequence) > 4:
            slug += "_etc"
        short_hash = hashlib.sha256("|".join(action_sequence).encode("utf-8")).hexdigest()[:6]
        return f"skill_{slug}_{short_hash}"[:80]

    @staticmethod
    def default_description(action_sequence: List[str]) -> str:
        return "Runs: " + " -> ".join(action_sequence)


def get_skill_generator() -> SkillGenerator:
    """Process-wide SkillGenerator singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SkillGenerator()
    return _instance
