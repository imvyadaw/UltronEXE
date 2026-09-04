"""
feedback_collector.py
========================
Collects feedback on ULTRON's actions/responses so the rest of
LEARNING_ENGINE has something to learn from:

  - explicit: user says "good job" / "no, that's wrong" / thumbs up-down
  - implicit: user immediately undoes/repeats/corrects an action
    (a strong implicit negative signal), or moves on without
    complaint (a weak implicit positive signal)

Everything is stored locally as structured JSON. Nothing here scores
or "punishes" the user - it only scores ULTRON's own actions, and
only ever on data the user's own session produced.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("ultron.feedback_collector")

DEFAULT_STORE = Path("ultron_data/learning/feedback_log.json")


class FeedbackType(str, Enum):
    EXPLICIT_POSITIVE = "explicit_positive"
    EXPLICIT_NEGATIVE = "explicit_negative"
    IMPLICIT_CORRECTION = "implicit_correction"  # user immediately redid/undid the action
    IMPLICIT_ACCEPTANCE = "implicit_acceptance"  # user moved on, no correction


@dataclass
class FeedbackEntry:
    action_id: str  # correlates to whatever ID the action/skill call used
    action: str
    feedback_type: str
    timestamp: str
    note: Optional[str] = None


class FeedbackCollector:
    """Records and retrieves feedback entries tied to specific assistant actions."""

    def __init__(self, store_path: Path = DEFAULT_STORE):
        self.store_path = Path(store_path)
        self._lock = threading.Lock()
        self.entries: List[FeedbackEntry] = []
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.entries = [FeedbackEntry(**e) for e in data]
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load feedback log (%s), starting fresh", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(e) for e in self.entries], indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    def record(self, action_id: str, action: str, feedback_type: FeedbackType, note: Optional[str] = None):
        with self._lock:
            entry = FeedbackEntry(
                action_id=action_id,
                action=action,
                feedback_type=feedback_type.value,
                timestamp=datetime.now().isoformat(timespec="seconds"),
                note=note,
            )
            self.entries.append(entry)
            self._save()
        logger.info("Feedback recorded: %s -> %s", action, feedback_type.value)
        return entry

    def positive(self, action_id: str, action: str, note: Optional[str] = None):
        return self.record(action_id, action, FeedbackType.EXPLICIT_POSITIVE, note)

    def negative(self, action_id: str, action: str, note: Optional[str] = None):
        return self.record(action_id, action, FeedbackType.EXPLICIT_NEGATIVE, note)

    def implicit_correction(self, action_id: str, action: str, note: Optional[str] = None):
        return self.record(action_id, action, FeedbackType.IMPLICIT_CORRECTION, note)

    def implicit_acceptance(self, action_id: str, action: str):
        return self.record(action_id, action, FeedbackType.IMPLICIT_ACCEPTANCE)

    def score_for_action(self, action: str) -> float:
        """Rough net-approval score in [-1, 1] for a given action type, across all recorded feedback."""
        weights = {
            FeedbackType.EXPLICIT_POSITIVE.value: 1.0,
            FeedbackType.IMPLICIT_ACCEPTANCE.value: 0.3,
            FeedbackType.IMPLICIT_CORRECTION.value: -0.7,
            FeedbackType.EXPLICIT_NEGATIVE.value: -1.0,
        }
        relevant = [e for e in self.entries if e.action == action]
        if not relevant:
            return 0.0
        total = sum(weights.get(e.feedback_type, 0.0) for e in relevant)
        return round(max(-1.0, min(1.0, total / len(relevant))), 3)

    def recent(self, limit: int = 20) -> List[FeedbackEntry]:
        return self.entries[-limit:]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fc = FeedbackCollector(store_path=Path("ultron_data/learning/_demo_feedback_log.json"))
    fc.positive("a1", "run_skill:whatsapp_send")
    fc.implicit_correction("a2", "run_skill:whatsapp_send", note="user immediately re-sent to a different contact")
    print("score:", fc.score_for_action("run_skill:whatsapp_send"))
