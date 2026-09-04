"""
behavior_modeler.py
=====================
Builds a lightweight statistical model of the user's action sequences
(what they tend to do, and what they tend to do *next*), so other
modules in PREDICTIVE_ENGINE can make informed guesses. This is a
plain frequency / first-order transition table, not a neural model -
it's fast, fully local, explainable, and cheap to update.

Storage: a single JSON file on disk (no telemetry, nothing leaves
the machine). Default path: ultron_data/predictive/behavior_model.json

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ultron.behavior_modeler")

DEFAULT_STORE = Path("ultron_data/predictive/behavior_model.json")


@dataclass
class ActionEvent:
    action: str  # e.g. "open_app:vscode", "run_skill:whatsapp_send"
    timestamp: str
    context: Dict[str, str] = field(default_factory=dict)  # e.g. {"hour": "9", "day": "Mon"}


class BehaviorModeler:
    """Tracks action history and maintains a first-order transition table."""

    def __init__(self, store_path: Path = DEFAULT_STORE, max_history: int = 5000):
        self.store_path = Path(store_path)
        self.max_history = max_history
        self._lock = threading.Lock()
        self.history: List[ActionEvent] = []
        # transitions[prev_action][next_action] = count
        self.transitions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.action_counts: Dict[str, int] = defaultdict(int)
        self._last_action: Optional[str] = None
        self._load()

    # -- persistence -----------------------------------------------------
    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.history = [ActionEvent(**e) for e in data.get("history", [])]
            self.action_counts = defaultdict(int, data.get("action_counts", {}))
            for prev, nexts in data.get("transitions", {}).items():
                self.transitions[prev] = defaultdict(int, nexts)
            self._last_action = data.get("last_action")
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load behavior model (%s), starting fresh", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "history": [vars(e) for e in self.history[-self.max_history :]],
            "action_counts": dict(self.action_counts),
            "transitions": {k: dict(v) for k, v in self.transitions.items()},
            "last_action": self._last_action,
        }
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    # -- recording ---------------------------------------------------------
    def record(self, action: str, context: Optional[Dict[str, str]] = None):
        """Record that `action` just happened."""
        with self._lock:
            event = ActionEvent(
                action=action, timestamp=datetime.now().isoformat(timespec="seconds"), context=context or {}
            )
            self.history.append(event)
            self.action_counts[action] += 1
            if self._last_action is not None:
                self.transitions[self._last_action][action] += 1
            self._last_action = action
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history :]
            self._save()
        logger.debug("Recorded action: %s", action)

    # -- querying ------------------------------------------------------------
    def most_common_actions(self, top_n: int = 10) -> List[tuple]:
        return sorted(self.action_counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]

    def likely_followers(self, action: str, top_n: int = 5) -> List[tuple]:
        """What tends to happen right after `action`, ranked by frequency."""
        followers = self.transitions.get(action, {})
        total = sum(followers.values()) or 1
        ranked = sorted(followers.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return [(name, count, round(count / total, 3)) for name, count in ranked]

    def last_action(self) -> Optional[str]:
        return self._last_action

    def reset(self):
        with self._lock:
            self.history.clear()
            self.transitions.clear()
            self.action_counts.clear()
            self._last_action = None
            self._save()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    model = BehaviorModeler(store_path=Path("ultron_data/predictive/_demo_behavior_model.json"))
    for act in [
        "open_app:vscode",
        "run_skill:git_status",
        "open_app:browser",
        "open_app:vscode",
        "run_skill:git_status",
        "run_skill:git_commit",
    ]:
        model.record(act)
    print("Most common:", model.most_common_actions())
    print("After open_app:vscode ->", model.likely_followers("open_app:vscode"))
