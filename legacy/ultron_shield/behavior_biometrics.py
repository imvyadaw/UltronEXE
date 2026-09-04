"""
behavior_biometrics.py
====================
Builds a lightweight statistical profile of *how* you type - keystroke
timing intervals and a couple of derived rhythm features - not *what*
you type. It never stores key identities or content, only inter-key
timing deltas, so this can't be used to reconstruct passwords or
messages even if the profile store were somehow read by something
else.

Intended use: a light, continuous "does this still look like the
same person typing" signal alongside whatever primary auth you use
(password, device pairing token, OS login) - not a replacement for
it. On a mismatch this only ever raises a `ProfileMismatch` for a
callback you register to react to (e.g. ask for a PIN, or hand off to
`intrusion_detector.py`); it never locks anything out on its own.

Pure standard library.
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("ultron.behavior_biometrics")

DEFAULT_STORE_PATH = "ultron_data/shield/typing_profile.json"
MIN_SAMPLES_FOR_PROFILE = 20
MIN_INTERVALS_PER_SAMPLE = 5


@dataclass
class TypingSample:
    """One burst of typing, represented only as inter-keystroke
    intervals in milliseconds - never the keys themselves."""

    intervals_ms: List[float]
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def mean_interval(self) -> float:
        return statistics.mean(self.intervals_ms) if self.intervals_ms else 0.0

    def stdev_interval(self) -> float:
        return statistics.pstdev(self.intervals_ms) if len(self.intervals_ms) > 1 else 0.0


@dataclass
class ProfileMismatch:
    z_score: float
    sample_mean_ms: float
    profile_mean_ms: float
    message: str


class BehaviorBiometrics:
    """Maintains a rolling mean/stdev typing-rhythm profile and flags
    samples that fall too many standard deviations outside it."""

    def __init__(self, store_path: str = DEFAULT_STORE_PATH, mismatch_z_threshold: float = 3.0):
        self.store_path = store_path
        self.mismatch_z_threshold = mismatch_z_threshold
        self._sample_means: List[float] = []
        self._load()

    def enroll(self, sample: TypingSample) -> None:
        """Add a sample to the baseline profile. Call this during a period
        you're confident it's really you (right after a fresh password/2FA login)."""
        if len(sample.intervals_ms) < MIN_INTERVALS_PER_SAMPLE:
            logger.debug("Skipped enrollment sample - too few intervals")
            return
        self._sample_means.append(sample.mean_interval())
        self._save()

    def is_enrolled(self) -> bool:
        return len(self._sample_means) >= MIN_SAMPLES_FOR_PROFILE

    def check(self, sample: TypingSample) -> Optional[ProfileMismatch]:
        """Compare a live sample against the enrolled profile. Returns None
        if it looks consistent (or if not enough profile data exists yet to
        judge - we never flag on an under-trained profile), or a
        ProfileMismatch describing how far off it was."""
        if not self.is_enrolled() or len(sample.intervals_ms) < MIN_INTERVALS_PER_SAMPLE:
            return None

        profile_mean = statistics.mean(self._sample_means)
        profile_stdev = statistics.pstdev(self._sample_means) or 1.0  # avoid div by zero
        sample_mean = sample.mean_interval()

        z = abs(sample_mean - profile_mean) / profile_stdev
        if z >= self.mismatch_z_threshold:
            logger.warning("Typing rhythm mismatch: z=%.2f", z)
            return ProfileMismatch(
                z_score=z,
                sample_mean_ms=sample_mean,
                profile_mean_ms=profile_mean,
                message=f"Typing rhythm is {z:.1f} standard deviations from the enrolled profile.",
            )
        return None

    def reset_profile(self) -> None:
        """Wipe the profile and start over - use if you've enrolled bad data,
        or if the profile owner has genuinely changed (new household member,
        RSI-related change in typing, etc.)."""
        self._sample_means = []
        self._save()
        logger.info("Typing profile reset")

    def profile_size(self) -> int:
        return len(self._sample_means)

    def _load(self) -> None:
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, "r") as f:
                self._sample_means = json.load(f).get("sample_means", [])
        except (json.JSONDecodeError, OSError):
            self._sample_means = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        with open(self.store_path, "w") as f:
            json.dump({"sample_means": self._sample_means}, f, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bio = BehaviorBiometrics(store_path="ultron_data/shield/_demo_typing_profile.json")

    # Simulate enrollment with fairly consistent ~120ms intervals.
    import random

    random.seed(0)
    for _ in range(MIN_SAMPLES_FOR_PROFILE):
        bio.enroll(TypingSample(intervals_ms=[120 + random.uniform(-10, 10) for _ in range(10)]))

    print("Enrolled:", bio.is_enrolled(), "size:", bio.profile_size())

    consistent = TypingSample(intervals_ms=[118, 122, 121, 119, 125, 117])
    print("Consistent sample check:", bio.check(consistent))

    very_different = TypingSample(intervals_ms=[400, 420, 390, 410, 405, 415])
    print("Different sample check:", bio.check(very_different))
