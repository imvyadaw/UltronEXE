"""Memory consolidator
====================
learning/pattern_detector.py (Phase 4.3) already turns *recent* episodes
into semantic/procedural knowledge, and its docstring is explicit that it
"only ever reinforces or creates - it never deletes a pattern or
procedure". That's the right call for a detector, but it leaves a gap:
nothing ever revisits *old* episodes that pattern_detector's recurrence
thresholds never fired on (a one-off task that never repeated enough
times to become a pattern), and memory/episodic/ has no bound - it just
grows forever.

This module is the "sleep consolidation" pass that closes that gap,
without doing any deleting itself (that's learning/forgetting.py's job,
kept as its own module for the same reason memory/forget.py is split
from the rest of memory/ - deletion stays in one auditable place):

    - digest_stale_episodes(): episodes past `older_than_days` that never
      got folded into any memory/semantic/ pattern (checked via
      SemanticMemory.all_source_episode_ids()) are grouped by `kind` and
      rolled into one compact "episode_digest" pattern per kind - a
      count + success rate + date range, with source_episode_ids set to
      everything it summarizes. That marks those episodes safe-to-prune:
      learning/forgetting.py only ever deletes an episode that already
      shows up in some pattern's source_episode_ids, so a digest is what
      turns "old" into "prunable" for a one-off episode that would
      otherwise never qualify.
    - merge_duplicate_patterns(): learning/pattern_detector.py's own
      add_pattern() already dedupes *exact* description matches, but
      near-duplicates worded slightly differently by different detection
      passes still end up as separate rows. This folds fuzzy matches
      (difflib, same tool used for wake-word matching elsewhere in this
      project) within a pattern_type into one, keeping the
      higher-confidence side and merging both source_episode_ids sets.

run_consolidation() runs pattern_detector first (so anything freshly
promotable is captured before the digest step looks at what's left
over), then both steps above. Intended to be called periodically by
learning/learning_scheduler.py, not on every episode.
"""

import difflib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from core.logger import get_logger
from memory.episodic import get_episodic_memory
from memory.semantic import get_semantic_pattern_memory
from learning.pattern_detector import get_pattern_detector

logger = get_logger("memory_consolidator")

DEFAULT_STALE_DAYS = 14
MIN_EPISODES_PER_DIGEST = 3  # don't bother digesting a kind with just 1-2 stragglers
DUPLICATE_SIMILARITY_THRESHOLD = 0.85


class MemoryConsolidator:
    """Rolls stale, never-promoted episodes into digest patterns and merges near-duplicate patterns."""

    def __init__(self):
        self.episodic = get_episodic_memory()
        self.semantic = get_semantic_pattern_memory()
        self.pattern_detector = get_pattern_detector()

    def run_consolidation(self, older_than_days: int = DEFAULT_STALE_DAYS) -> Dict:
        """Full consolidation pass. Safe to call repeatedly (e.g. nightly) -
        every step here is idempotent: an already-digested episode is
        skipped, and an already-merged duplicate won't be found again."""
        try:
            detection = self.pattern_detector.run_detection()
            digest = self.digest_stale_episodes(older_than_days=older_than_days)
            merge = self.merge_duplicate_patterns()
            return {
                "pattern_detection": detection,
                "digest": digest,
                "merge": merge,
            }
        except Exception as e:
            logger.error(f"run_consolidation() failed: {e}")
            return {"error": str(e)}

    def digest_stale_episodes(
        self, older_than_days: int = DEFAULT_STALE_DAYS, min_per_digest: int = MIN_EPISODES_PER_DIGEST
    ) -> Dict:
        """Group undigested episodes older than `older_than_days` by kind
        and file one 'episode_digest' semantic pattern per kind covering
        them, so they stop being permanently un-prunable stragglers."""
        try:
            cutoff = (datetime.now() - timedelta(days=older_than_days)).timestamp()
            already_digested = self.semantic.all_source_episode_ids()

            old = self.episodic.recent_episodes(limit=1000)
            if "error" in old:
                return old
            candidates = [
                ep
                for ep in old["episodes"]
                if ep["episode_id"] not in already_digested
                and ep["started_at"] is not None
                and ep["started_at"] < cutoff
                and ep["ended_at"] is not None  # only fold in episodes that actually finished
            ]

            by_kind: Dict[str, List[Dict]] = {}
            for ep in candidates:
                by_kind.setdefault(ep["kind"], []).append(ep)

            digested = []
            for kind, episodes in by_kind.items():
                if len(episodes) < min_per_digest:
                    continue
                successes = sum(1 for e in episodes if e["success"])
                total = len(episodes)
                started = [e["started_at"] for e in episodes]
                result = self.semantic.add_pattern(
                    pattern_type="episode_digest",
                    description=f"{total} '{kind}' episodes from "
                    f"{datetime.fromtimestamp(min(started)):%Y-%m-%d} to "
                    f"{datetime.fromtimestamp(max(started)):%Y-%m-%d}, "
                    f"{successes}/{total} succeeded",
                    trigger_condition=f"kind={kind}",
                    typical_outcome="success" if successes >= total / 2 else "failure",
                    confidence=0.5,
                    source_episode_ids=[e["episode_id"] for e in episodes],
                )
                if "error" not in result:
                    digested.append({"kind": kind, "episode_count": total, "pattern_id": result["pattern_id"]})
            return {"digested_kinds": digested, "count": len(digested)}
        except Exception as e:
            logger.error(f"digest_stale_episodes() failed: {e}")
            return {"error": str(e)}

    def merge_duplicate_patterns(self, similarity_threshold: float = DUPLICATE_SIMILARITY_THRESHOLD) -> Dict:
        """Fold near-duplicate descriptions (same pattern_type, fuzzy
        text match) into one - keeps the row with the higher confidence,
        reinforces it with the other's observations, and removes the
        loser via SemanticMemory._delete_pattern()."""
        try:
            all_patterns = self.semantic.get_patterns()
            if "error" in all_patterns:
                return all_patterns
            by_type: Dict[str, List[Dict]] = {}
            for p in all_patterns["patterns"]:
                by_type.setdefault(p["pattern_type"], []).append(p)

            merged = []
            for ptype, patterns in by_type.items():
                used = set()
                for i, a in enumerate(patterns):
                    if a["id"] in used:
                        continue
                    for b in patterns[i + 1 :]:
                        if b["id"] in used:
                            continue
                        ratio = difflib.SequenceMatcher(None, a["description"], b["description"]).ratio()
                        if ratio >= similarity_threshold:
                            keeper, loser = (a, b) if a["confidence"] >= b["confidence"] else (b, a)
                            self.semantic.reinforce_pattern(
                                keeper["id"], source_episode_ids=loser.get("source_episode_ids", [])
                            )
                            self.semantic._delete_pattern(loser["id"])
                            used.add(loser["id"])
                            merged.append({"pattern_type": ptype, "kept": keeper["id"], "removed": loser["id"]})
            return {"merged": merged, "count": len(merged)}
        except Exception as e:
            logger.error(f"merge_duplicate_patterns() failed: {e}")
            return {"error": str(e)}


_memory_consolidator: Optional[MemoryConsolidator] = None


def get_memory_consolidator() -> MemoryConsolidator:
    global _memory_consolidator
    if _memory_consolidator is None:
        _memory_consolidator = MemoryConsolidator()
    return _memory_consolidator
