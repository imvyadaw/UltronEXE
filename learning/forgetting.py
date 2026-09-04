"""Forgetting
==========
memory/forget.py is the *manual*, user-directed way to delete something
Ultron remembers - explicit, audited, and (for a full wipe) confirm-gated.
It has no reach into learning/pattern_detector.py's patterns or
memory/episodic/'s raw episodes on purpose, and both of those modules'
own docstrings say they never delete anything themselves. Left alone,
that means detected-but-never-reconfirmed patterns and old episodes
accumulate forever with no automatic cleanup - "self-generated knowledge"
that nobody ever revisits doesn't quietly drop in relevance the way a
human's does.

This module is that automatic, background counterpart: it applies
learning/confidence.py's time-decay curve to every semantic pattern *at
read time* (nothing stored is rewritten - same read-time-only spirit as
confidence.py's own docstring), and prunes the ones that have decayed
past a floor and were never well-established (`observation_count` below
`PROTECT_MIN_OBSERVATIONS` - a regularity seen many times is kept
regardless of age, since repetition itself is evidence it still
matters). Episodes are only ever pruned once learning/memory_consolidator.py
has folded them into a pattern's source_episode_ids - see
SemanticMemory.all_source_episode_ids() - so a raw episode never
disappears before whatever was learned from it has been captured
elsewhere.

Every prune is written to storage/learning/forgetting_log.json first
(JSON, not SQLite - same trade-off as learning/failure_learner.py's
lessons file: a personal assistant prunes at most a few dozen things a
week, and a plain file is easy to audit by hand). No confirm=True gate
like memory/forget.py's forget_everything() - what's pruned here is
either a low-confidence, rarely-reconfirmed pattern or an episode
that's already been summarized elsewhere, not a fact/person/place the
user explicitly asked Ultron to remember.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from config import STORAGE_DIR
from core.logger import get_logger
from memory.episodic import get_episodic_memory
from memory.semantic import get_semantic_pattern_memory
from learning.confidence import apply_time_decay, DECAY_FLOOR

logger = get_logger("forgetting")

LOG_PATH = STORAGE_DIR / "learning" / "forgetting_log.json"

# apply_time_decay() asymptotically approaches DECAY_FLOOR (0.2) and never
# goes below it for any pattern that started at or above the floor (which
# is every pattern - see memory/semantic/semantic_memory.py's
# DEFAULT_CONFIDENCE=0.4) - a threshold below DECAY_FLOOR would mean
# nothing ever decays far enough to prune. Sitting just above the floor
# means "has decayed nearly all the way toward stale", not "any decay at all".
MIN_RETAIN_CONFIDENCE = DECAY_FLOOR + 0.05
PROTECT_MIN_OBSERVATIONS = 5  # seen this many times or more -> kept regardless of decay
PROTECTED_PATTERN_TYPES = {"episode_digest"}  # already-compact summaries; nothing to gain by pruning further

DEFAULT_EPISODE_STALE_DAYS = 30


class Forgetting:
    """Decays low-value semantic patterns and prunes already-digested stale episodes."""

    def __init__(self):
        self.semantic = get_semantic_pattern_memory()
        self.episodic = get_episodic_memory()
        self._log = self._load_log()

    def run_decay_cycle(self, episode_stale_days: int = DEFAULT_EPISODE_STALE_DAYS) -> Dict:
        """Full pass: decay-and-prune patterns, then prune whatever
        episodes that leaves eligible. Safe to call repeatedly - already
        current-confidence patterns and already-pruned episodes are
        simply skipped."""
        try:
            patterns = self.decay_and_prune_patterns()
            episodes = self.prune_digested_episodes(older_than_days=episode_stale_days)
            return {"patterns": patterns, "episodes": episodes}
        except Exception as e:
            logger.error(f"run_decay_cycle() failed: {e}")
            return {"error": str(e)}

    def decay_and_prune_patterns(
        self,
        min_retain_confidence: float = MIN_RETAIN_CONFIDENCE,
        protect_min_observations: int = PROTECT_MIN_OBSERVATIONS,
    ) -> Dict:
        """Apply time-decay (read-time only, nothing stored is rewritten)
        to every pattern's confidence, and delete the ones that have
        decayed past the floor without ever being well-established."""
        try:
            all_patterns = self.semantic.get_patterns()
            if "error" in all_patterns:
                return all_patterns
            pruned = []
            for p in all_patterns["patterns"]:
                if p["pattern_type"] in PROTECTED_PATTERN_TYPES:
                    continue
                if p["observation_count"] >= protect_min_observations:
                    continue
                decayed = apply_time_decay(p["confidence"], p["updated_at"])
                if decayed < min_retain_confidence:
                    if self.semantic._delete_pattern(p["id"]):
                        entry = {
                            "action": "prune_pattern",
                            "pattern_id": p["id"],
                            "pattern_type": p["pattern_type"],
                            "description": p["description"],
                            "decayed_confidence": decayed,
                            "observation_count": p["observation_count"],
                            "pruned_at": time.time(),
                        }
                        self._append_log(entry)
                        pruned.append(entry)
            return {"pruned": pruned, "count": len(pruned)}
        except Exception as e:
            logger.error(f"decay_and_prune_patterns() failed: {e}")
            return {"error": str(e)}

    def prune_digested_episodes(self, older_than_days: int = DEFAULT_EPISODE_STALE_DAYS) -> Dict:
        """Delete raw episode rows that are both older than
        `older_than_days` AND already referenced in some semantic
        pattern's source_episode_ids (i.e. learning/memory_consolidator.py
        has already folded whatever they taught into a durable pattern).
        Never touches an episode that hasn't been digested yet."""
        try:
            cutoff = (datetime.now() - timedelta(days=older_than_days)).timestamp()
            digested_ids = self.semantic.all_source_episode_ids()
            old = self.episodic.recent_episodes(limit=1000)
            if "error" in old:
                return old
            pruned = []
            for ep in old["episodes"]:
                if ep["episode_id"] not in digested_ids:
                    continue
                if ep["started_at"] is None or ep["started_at"] >= cutoff:
                    continue
                if self.episodic._delete_episode(ep["episode_id"]):
                    entry = {
                        "action": "prune_episode",
                        "episode_id": ep["episode_id"],
                        "kind": ep["kind"],
                        "pruned_at": time.time(),
                    }
                    self._append_log(entry)
                    pruned.append(entry)
            return {"pruned": pruned, "count": len(pruned)}
        except Exception as e:
            logger.error(f"prune_digested_episodes() failed: {e}")
            return {"error": str(e)}

    def get_log(self, limit: int = 20) -> Dict:
        entries = self._log[-limit:][::-1]
        return {"count": len(entries), "entries": entries}

    # -- persistence -----------------------------------------------------
    def _append_log(self, entry: Dict) -> None:
        self._log.append(entry)
        self._save_log()

    def _load_log(self) -> List[Dict]:
        if not LOG_PATH.exists():
            return []
        try:
            return json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load forgetting log ({e}), starting fresh")
            return []

    def _save_log(self) -> None:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(json.dumps(self._log, indent=2, ensure_ascii=False), encoding="utf-8")


_forgetting: Optional[Forgetting] = None


def get_forgetting() -> Forgetting:
    global _forgetting
    if _forgetting is None:
        _forgetting = Forgetting()
    return _forgetting
