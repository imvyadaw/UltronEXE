"""
mistake_learner.py
=====================
Keeps a durable log of things that went wrong (a failed action, a
user correction, an explicit "no, don't do that") and turns repeat
offenders into caution flags: before ULTRON repeats an action that
has a bad track record, callers can check `should_caution()` and
either double-check with the user or pick an alternative.

This deliberately never *silently blocks* an action outright - it
only raises a flag with the reason, so a human (or a higher-level
policy layer) stays in the loop for the actual decision.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("ultron.mistake_learner")

DEFAULT_STORE = Path("ultron_data/learning/mistakes_log.json")


@dataclass
class Mistake:
    action: str
    description: str
    timestamp: str
    context: Optional[str] = None


class MistakeLearner:
    """Tracks repeated mistakes per action and flags actions with a poor track record."""

    def __init__(self, store_path: Path = DEFAULT_STORE, caution_threshold: int = 2):
        self.store_path = Path(store_path)
        self.caution_threshold = caution_threshold
        self._lock = threading.Lock()
        self.mistakes: List[Mistake] = []
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.mistakes = [Mistake(**m) for m in data]
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load mistakes log (%s), starting fresh", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(m) for m in self.mistakes], indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    def record_mistake(self, action: str, description: str, context: Optional[str] = None):
        with self._lock:
            m = Mistake(
                action=action,
                description=description,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                context=context,
            )
            self.mistakes.append(m)
            self._save()
        logger.info("Mistake recorded for '%s': %s", action, description)
        return m

    def mistake_count(self, action: str) -> int:
        return sum(1 for m in self.mistakes if m.action == action)

    def should_caution(self, action: str) -> Optional[str]:
        """Returns a human-readable caution reason if `action` has a rough track record, else None."""
        relevant = [m for m in self.mistakes if m.action == action]
        if len(relevant) < self.caution_threshold:
            return None
        recent_descriptions = "; ".join(m.description for m in relevant[-3:])
        return (
            f"'{action}' has gone wrong {len(relevant)}x before "
            f"(most recently: {recent_descriptions}) - consider confirming with the user first"
        )

    def clear(self, action: Optional[str] = None):
        """Clear mistake history for one action, or everything if action is None."""
        with self._lock:
            if action:
                self.mistakes = [m for m in self.mistakes if m.action != action]
            else:
                self.mistakes.clear()
            self._save()

    def recent(self, limit: int = 20) -> List[Mistake]:
        return self.mistakes[-limit:]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ml = MistakeLearner(store_path=Path("ultron_data/learning/_demo_mistakes_log.json"), caution_threshold=2)
    ml.record_mistake("run_skill:send_email", "sent to wrong contact")
    ml.record_mistake("run_skill:send_email", "user immediately asked to recall it")
    print(ml.should_caution("run_skill:send_email"))
