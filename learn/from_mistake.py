"""
From Mistake (LEARN)
========================
A corrected-pairs log: log_mistake(context, correction) records that
Ultron got `context` wrong and `correction` is what it should have
done/said instead; suggest_correction(context) looks up whether
anything similar has been corrected before, so the same mistake isn't
repeated silently. Matching uses stdlib `difflib` against every past
`context` on file - no embedding model, no external dependency -
which is approximate on purpose: it surfaces close-but-not-identical
contexts too (ranked lower) rather than requiring an exact string
match that would miss "turn off the living room light" vs "turn off
living room lights".

This module only stores and retrieves; it never applies a correction
automatically. improve_self.py in this same package is where a
caller would fold suggest_correction() results into an actual
decision.
"""

import difflib
import json
import os
import time
from typing import Dict, List, Optional

STATE_FILE_ENV = "AI_EVOLUTION_MISTAKES_FILE"
DEFAULT_STATE_FILE = "data/ai_evolution/mistakes.json"
MATCH_THRESHOLD = 0.6


class FromMistake:
    """Corrected-pairs log with fuzzy lookup. Use get_from_mistake()."""

    def _state_path(self) -> str:
        path = os.environ.get(STATE_FILE_ENV, DEFAULT_STATE_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        return path

    def _read_state(self) -> Dict:
        path = self._state_path()
        if not os.path.exists(path):
            return {"mistakes": []}
        with open(path) as fh:
            return json.load(fh)

    def _write_state(self, data: Dict) -> None:
        with open(self._state_path(), "w") as fh:
            json.dump(data, fh)

    def log_mistake(self, context: str, correction: str, note: Optional[str] = None) -> Dict:
        """Records that `context` was handled wrong and `correction`
        is the right way, with an optional free-text `note` on why.
        Every call appends a new entry rather than overwriting a
        prior one for the same context, so repeated mistakes on
        similar contexts are all visible in get_all(). Returns
        {"success": bool, "error": Optional[str]}."""
        if not context or not correction:
            return {"success": False, "error": "context and correction are both required"}
        data = self._read_state()
        data["mistakes"].append(
            {
                "context": context,
                "correction": correction,
                "note": note,
                "timestamp": time.time(),
            }
        )
        self._write_state(data)
        return {"success": True, "error": None}

    def suggest_correction(self, context: str, top_n: int = 3) -> List[Dict]:
        """Ranks up to `top_n` past mistakes whose logged `context`
        most closely matches the given `context`, by difflib
        similarity ratio, highest first, filtering out anything below
        MATCH_THRESHOLD. Returns a list of {"context": str,
        "correction": str, "note": Optional[str], "similarity":
        float} - empty if nothing on file clears the threshold."""
        if not context:
            return []
        candidates = []
        for entry in self._read_state()["mistakes"]:
            ratio = difflib.SequenceMatcher(None, context.lower(), entry["context"].lower()).ratio()
            if ratio >= MATCH_THRESHOLD:
                candidates.append({**entry, "similarity": round(ratio, 3)})
        candidates.sort(key=lambda c: c["similarity"], reverse=True)
        return candidates[:top_n]

    def get_all(self) -> List[Dict]:
        """Every mistake ever logged, oldest first, unfiltered."""
        return self._read_state()["mistakes"]


_from_mistake: Optional[FromMistake] = None


def get_from_mistake() -> FromMistake:
    global _from_mistake
    if _from_mistake is None:
        _from_mistake = FromMistake()
    return _from_mistake
