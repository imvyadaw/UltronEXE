"""
Usage tracker
=============
Persists Groq API call/token usage to storage/cache/mj_usage.json so
"how much have I used the API" survives restarts. This file was referenced
by ai/cloud_models/groq_client.py (`self.usage_tracker = UsageTracker()`,
`increment_usage()`) and ai/tool_runtime.py (`get_usage_summary()` behind
the `get_api_usage` tool) but didn't exist anywhere in the project - which
meant importing either of those modules, and therefore the entire
tool-calling loop on both the cloud and local AI backends, raised
`ModuleNotFoundError` before this fix.
bh
"""
import json
import time
from pathlib import Path
from typing import Dict

STORE_PATH = Path(__file__).resolve().parent / "mj_usage.json"


class UsageTracker:
    """Tracks Groq API calls and tokens used, per model, persisted to disk."""

    def __init__(self, store_path: str = None):
        self.store_path = Path(store_path) if store_path else STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> Dict:
        if not self.store_path.exists():
            return {"models": {}, "total_calls": 0, "total_tokens": 0, "started_at": time.time()}
        try:
            return json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"models": {}, "total_calls": 0, "total_tokens": 0, "started_at": time.time()}

    def _save(self) -> None:
        try:
            self.store_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError:
            from core.error_trace import log_swallowed as _lsw
            _lsw("storage.cache.usage_tracker._save")

    def increment_usage(self, model: str, tokens: int) -> None:
        """Record one API call against `model`, adding `tokens` to its running total."""
        if not model:
            return
        models = self._data.setdefault("models", {})
        entry = models.setdefault(model, {"calls": 0, "tokens": 0})
        entry["calls"] += 1
        entry["tokens"] += max(0, int(tokens or 0))

        self._data["total_calls"] = self._data.get("total_calls", 0) + 1
        self._data["total_tokens"] = self._data.get("total_tokens", 0) + max(0, int(tokens or 0))
        self._data["last_used_at"] = time.time()
        self._save()

    def get_usage_summary(self) -> Dict:
        """Return the full usage summary - what the `get_api_usage` tool reports."""
        return {
            "success": True,
            "total_calls": self._data.get("total_calls", 0),
            "total_tokens": self._data.get("total_tokens", 0),
            "by_model": self._data.get("models", {}),
            "tracking_since": self._data.get("started_at"),
            "last_used_at": self._data.get("last_used_at"),
        }

    def reset(self) -> Dict:
        """Clear all recorded usage (e.g. for a new billing period)."""
        self._data = {"models": {}, "total_calls": 0, "total_tokens": 0, "started_at": time.time()}
        self._save()
        return {"success": True, "action": "usage reset"}
