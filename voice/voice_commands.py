"""
Voice commands
===============
A persistent, user-programmable phrase -> tool mapping, separate from
core/intent_router.py's built-in regex patterns (workflow/background/
task-status, which are fixed) and ai/local_router.py's hardcoded system
shortcuts. This is for the user's *own* custom shortcuts - "add a voice
command 'good morning' that runs my morning_routine workflow" - matched
fuzzily (difflib) so minor STT mis-transcriptions ("good morning sir"
vs "good morning") still hit, without needing an LLM round-trip.

Persisted as JSON under storage/cache/voice_commands.json so registered
commands survive a restart.
"""

import difflib
import json
import re
from pathlib import Path
from typing import Dict, Optional

MATCH_THRESHOLD = 0.72  # difflib ratio - tuned loose enough for STT noise,
# tight enough not to fire on unrelated speech


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


class VoiceCommandRegistry:
    """Register short spoken phrases as shortcuts for a tool call (or a
    saved workflow, via tool_name="run_advanced_workflow")."""

    def __init__(self):
        from config import CACHE_DIR

        self._path = Path(CACHE_DIR) / "voice_commands.json"
        self._commands: Dict[str, Dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._commands = json.load(f)
            except Exception:
                self._commands = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._commands, f, indent=2)

    def add_command(self, phrase: str, tool_name: str, arguments: Optional[Dict] = None, label: str = "") -> Dict:
        key = _normalize(phrase)
        if not key:
            return {"error": "Empty phrase"}
        self._commands[key] = {
            "phrase": phrase,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "label": label or phrase,
        }
        self._save()
        return {"success": True, "phrase": phrase, "tool_name": tool_name}

    def remove_command(self, phrase: str) -> Dict:
        key = _normalize(phrase)
        if key not in self._commands:
            return {"error": f"No voice command matching '{phrase}'"}
        del self._commands[key]
        self._save()
        return {"success": True, "removed": phrase}

    def list_commands(self) -> Dict:
        return {"count": len(self._commands), "commands": list(self._commands.values())}

    def match(self, text: str) -> Optional[Dict]:
        """Fuzzy-match spoken `text` against registered phrases. Returns
        the matched command dict (with a "score" added), or None if
        nothing clears MATCH_THRESHOLD."""
        if not self._commands:
            return None
        normalized = _normalize(text)
        best_key, best_score = None, 0.0
        for key in self._commands:
            score = difflib.SequenceMatcher(None, normalized, key).ratio()
            # A registered phrase fully contained in a longer spoken
            # utterance ("ultron good morning please") should still count.
            if key in normalized:
                score = max(score, 0.9)
            if score > best_score:
                best_key, best_score = key, score
        if best_key and best_score >= MATCH_THRESHOLD:
            result = dict(self._commands[best_key])
            result["score"] = round(best_score, 3)
            return result
        return None

    def execute_if_matched(self, text: str) -> Optional[Dict]:
        """Convenience: match `text` and, if it hits, run the mapped tool
        via core.executor. Returns the execution result dict, or None if
        nothing matched (caller should fall through to normal handling)."""
        command = self.match(text)
        if command is None:
            return None
        from ai.tool_runtime import execute_tool_call as execute_tool

        raw = execute_tool(command["tool_name"], command["arguments"])
        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            result = raw
        return {"matched_phrase": command["phrase"], "score": command["score"], "result": result}


_instance: "VoiceCommandRegistry" = None


def get_voice_command_registry() -> VoiceCommandRegistry:
    global _instance
    if _instance is None:
        _instance = VoiceCommandRegistry()
    return _instance
