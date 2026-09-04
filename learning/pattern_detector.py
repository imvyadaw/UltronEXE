"""Pattern detector
================
Mines memory/episodic/ (bounded task episodes, Phase 4.3) for
regularities that are worth generalizing, and consolidates them
upward:
    - a step-sequence that recurs across several successful episodes
      of the same kind -> promoted into memory/procedural/ as a
      reusable procedure.
    - a kind of episode that reliably happens around the same time of
      day -> written to memory/semantic/ as a timing pattern.
    - any regularity that keeps getting re-observed -> reinforced
      (not re-created) via memory/semantic/'s confidence bookkeeping.

Distinct from intelligence/skill_builder/workflow_detector.py, which
mines the ambient raw action-name stream for n-grams to suggest as
skills. This operates one level up, over memory/episodic/'s bounded,
outcome-scored episodes rather than a flat action log, and its output
is generalized *knowledge* (semantic patterns, promoted procedures),
not a skill suggestion queue. The two can coexist - workflow_detector
answers "is this worth automating", pattern_detector answers "is this
worth remembering as a regularity".

Detection is deliberately simple/heuristic (count-based thresholds,
no ML), same spirit as the rest of Phase 4: it needs to be cheap
enough to run after every few episodes, not perfectly precise.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from core.logger import get_logger
from memory.episodic import get_episodic_memory
from memory.semantic import get_semantic_pattern_memory
from memory.procedural import get_procedural_outcome_memory
from memory.user import get_user_model

logger = get_logger("pattern_detector")

MIN_SEQUENCE_OCCURRENCES = 3  # same step-sequence seen at least this many times before promoting
MIN_TIME_OCCURRENCES = 3  # same kind seen in the same hour-bucket at least this many times
MIN_EPISODES_FOR_TIME_PATTERN = 5
HOUR_BUCKET_SIZE = 2  # group into 2-hour windows so "6:05pm" and "7:40pm" still count as one bucket
TRAIT_PROMOTION_CONFIDENCE = 0.75  # a semantic pattern this confident about the user gets promoted to memory/user/


class PatternDetector:
    """Scans recent episodes for recurring step-sequences and timing
    regularities, and files what it finds into memory/semantic/ and
    memory/procedural/."""

    def __init__(self):
        self.episodic = get_episodic_memory()
        self.semantic = get_semantic_pattern_memory()
        self.procedural = get_procedural_outcome_memory()
        self.user_model = get_user_model()

    def run_detection(self, lookback: int = 200) -> Dict:
        """Run every detector over the most recent `lookback` episodes.
        Safe to call repeatedly (e.g. after each episode, or on a
        schedule) - existing patterns are reinforced, not duplicated."""
        try:
            episodes = self.episodic.recent_episodes(limit=lookback)["episodes"]
            sequence_result = self.detect_sequence_patterns(episodes)
            timing_result = self.detect_timing_patterns(episodes)
            reliability_result = self.detect_reliability_patterns()
            return {
                "episodes_scanned": len(episodes),
                "sequence_patterns": sequence_result,
                "timing_patterns": timing_result,
                "reliability_patterns": reliability_result,
            }
        except Exception as e:
            logger.error(f"run_detection() failed: {e}")
            return {"error": str(e)}

    # -- recurring step-sequences -> promote to a procedure --------------
    def detect_sequence_patterns(self, episodes: Optional[List[Dict]] = None) -> Dict:
        """Group successful episodes by kind, and if the exact same
        ordered sequence of step descriptions recurs often enough within
        a kind, save it as a reusable procedure."""
        try:
            episodes = episodes if episodes is not None else self.episodic.recent_episodes(limit=200)["episodes"]
            by_kind: Dict[str, List[Dict]] = defaultdict(list)
            for ep in episodes:
                if ep.get("success"):
                    by_kind[ep["kind"]].append(ep)

            promoted = []
            for kind, kind_episodes in by_kind.items():
                sequences = []
                for ep in kind_episodes:
                    full = self.episodic.get_episode(ep["episode_id"])
                    steps = tuple(s["description"] for s in full.get("steps", []) if s["success"])
                    if steps:
                        sequences.append((ep["episode_id"], steps))

                counts = Counter(seq for _, seq in sequences)
                for seq, count in counts.items():
                    if count < MIN_SEQUENCE_OCCURRENCES:
                        continue
                    name = self._procedure_name(kind, seq)
                    existing = self.procedural.get_procedure(name)
                    if "error" in existing:
                        steps_payload = [{"tool": step, "arguments": {}} for step in seq]
                        self.procedural.save_procedure(
                            name,
                            steps_payload,
                            description=f"Auto-detected from {count} successful '{kind}' episodes",
                            goal_keywords=kind,
                        )
                        promoted.append(name)
                    self.semantic.add_pattern(
                        pattern_type="recurring_sequence",
                        description=f"'{kind}' episodes tend to follow the same {len(seq)}-step sequence",
                        trigger_condition=f"kind={kind}",
                        typical_outcome="success",
                        confidence=min(0.4 + 0.05 * count, 0.9),
                        source_episode_ids=[eid for eid, s in sequences if s == seq],
                    )
            return {"promoted_procedures": promoted, "count": len(promoted)}
        except Exception as e:
            logger.error(f"detect_sequence_patterns() failed: {e}")
            return {"error": str(e)}

    # -- timing regularities -> semantic pattern (+ user trait) ----------
    def detect_timing_patterns(self, episodes: Optional[List[Dict]] = None) -> Dict:
        """If a `kind` of episode keeps starting in the same rough time-of-day
        window, record that as a pattern - and if it's confident and
        common enough, promote it into the user's profile."""
        try:
            episodes = episodes if episodes is not None else self.episodic.recent_episodes(limit=200)["episodes"]
            by_kind: Dict[str, List[float]] = defaultdict(list)
            for ep in episodes:
                if ep.get("started_at"):
                    by_kind[ep["kind"]].append(ep["started_at"])

            recorded = []
            for kind, timestamps in by_kind.items():
                if len(timestamps) < MIN_EPISODES_FOR_TIME_PATTERN:
                    continue
                buckets = Counter(self._hour_bucket(ts) for ts in timestamps)
                bucket, count = buckets.most_common(1)[0]
                if count < MIN_TIME_OCCURRENCES:
                    continue
                description = f"'{kind}' episodes tend to start around {bucket}"
                result = self.semantic.add_pattern(
                    pattern_type="timing",
                    description=description,
                    trigger_condition=f"kind={kind}",
                    typical_outcome=bucket,
                    confidence=min(0.4 + 0.06 * count, 0.9),
                )
                recorded.append({"kind": kind, "window": bucket, "occurrences": count})
                if result.get("confidence", 0) >= TRAIT_PROMOTION_CONFIDENCE:
                    self.user_model.set_trait(
                        dimension=f"typical_time_for_{kind}",
                        value=bucket,
                        confidence=result["confidence"],
                        evidence=description,
                    )
            return {"recorded": recorded, "count": len(recorded)}
        except Exception as e:
            logger.error(f"detect_timing_patterns() failed: {e}")
            return {"error": str(e)}

    # -- reliability regularities -> semantic pattern ---------------------
    def detect_reliability_patterns(self) -> Dict:
        """Episode kinds with a consistently low (or high) success rate
        are themselves a pattern worth remembering - this is the read-only
        counterpart to learning/failure_learner.py's caution-flagging,
        aimed at memory rather than at blocking anything."""
        try:
            rates = self.episodic.failure_rate_by_kind()
            if "error" in rates:
                return rates
            recorded = []
            for kind, stats in rates.items():
                if stats["attempts"] < MIN_TIME_OCCURRENCES or stats["success_rate"] is None:
                    continue
                if stats["success_rate"] <= 0.5:
                    self.semantic.add_pattern(
                        pattern_type="reliability",
                        description=f"'{kind}' episodes succeed only about {int(stats['success_rate'] * 100)}% of the time",
                        trigger_condition=f"kind={kind}",
                        typical_outcome="failure",
                        confidence=min(0.4 + 0.05 * stats["attempts"], 0.9),
                    )
                    recorded.append(kind)
            return {"flagged_kinds": recorded, "count": len(recorded)}
        except Exception as e:
            logger.error(f"detect_reliability_patterns() failed: {e}")
            return {"error": str(e)}

    @staticmethod
    def _hour_bucket(timestamp: float) -> str:
        hour = datetime.fromtimestamp(timestamp).hour
        bucket_start = (hour // HOUR_BUCKET_SIZE) * HOUR_BUCKET_SIZE
        bucket_end = bucket_start + HOUR_BUCKET_SIZE
        return f"{bucket_start:02d}:00-{bucket_end:02d}:00"

    @staticmethod
    def _procedure_name(kind: str, steps: tuple) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", kind.lower()).strip("_")
        return f"auto_{slug}_{len(steps)}step"


_pattern_detector: Optional[PatternDetector] = None


def get_pattern_detector() -> PatternDetector:
    global _pattern_detector
    if _pattern_detector is None:
        _pattern_detector = PatternDetector()
    return _pattern_detector
