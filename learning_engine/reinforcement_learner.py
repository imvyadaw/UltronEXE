"""
reinforcement_learner.py
===========================
A small, local epsilon-greedy contextual-bandit-style learner. When
there are multiple valid ways to handle a request (e.g. three
different phrasings ULTRON could reply with, or two different skills
that could both satisfy an intent), this module picks one, and
FeedbackCollector's resulting score updates that option's running
value estimate - so ULTRON gradually favors the choices that have
actually gone well for this user.

This is intentionally simple (no gradients, no external calls) so
its behavior is always inspectable: `values` is just a plain dict of
running averages you can print and reason about directly.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import json
import logging
import random
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("ultron.reinforcement_learner")

DEFAULT_STORE = Path("ultron_data/learning/rl_values.json")


@dataclass
class ArmStats:
    count: int = 0
    value: float = 0.0  # running average reward, roughly in [-1, 1]


class ReinforcementLearner:
    """Epsilon-greedy multi-armed bandit, one independent bandit per `context` key."""

    def __init__(self, store_path: Path = DEFAULT_STORE, epsilon: float = 0.1):
        self.store_path = Path(store_path)
        self.epsilon = epsilon
        self._lock = threading.Lock()
        # stats[context][option] = ArmStats
        self.stats: Dict[str, Dict[str, ArmStats]] = {}
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.stats = {ctx: {opt: ArmStats(**s) for opt, s in options.items()} for ctx, options in raw.items()}
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load RL values (%s), starting fresh", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            ctx: {opt: {"count": s.count, "value": s.value} for opt, s in options.items()}
            for ctx, options in self.stats.items()
        }
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    def choose(self, context: str, options: List[str]) -> str:
        """Pick an option for `context` using epsilon-greedy selection."""
        if not options:
            raise ValueError("choose() needs at least one option")
        with self._lock:
            ctx_stats = self.stats.setdefault(context, {})
            for opt in options:
                ctx_stats.setdefault(opt, ArmStats())

            if random.random() < self.epsilon:
                choice = random.choice(options)
                logger.debug("RL explore: context=%s -> %s", context, choice)
                return choice

            choice = max(options, key=lambda o: ctx_stats[o].value)
            logger.debug("RL exploit: context=%s -> %s (value=%.3f)", context, choice, ctx_stats[choice].value)
            return choice

    def reward(self, context: str, option: str, reward: float):
        """Update the running value estimate for (context, option) with an observed reward in [-1, 1]."""
        reward = max(-1.0, min(1.0, reward))
        with self._lock:
            ctx_stats = self.stats.setdefault(context, {})
            arm = ctx_stats.setdefault(option, ArmStats())
            arm.count += 1
            # incremental running average
            arm.value += (reward - arm.value) / arm.count
            self._save()
        logger.info("RL reward: context=%s option=%s reward=%.2f -> value=%.3f", context, option, reward, arm.value)

    def best(self, context: str) -> str | None:
        ctx_stats = self.stats.get(context)
        if not ctx_stats:
            return None
        return max(ctx_stats, key=lambda o: ctx_stats[o].value)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rl = ReinforcementLearner(store_path=Path("ultron_data/learning/_demo_rl_values.json"), epsilon=0.2)
    opts = ["reply_formal", "reply_casual"]
    choice = rl.choose("greeting_style", opts)
    rl.reward("greeting_style", choice, reward=0.8)
    print("best so far:", rl.best("greeting_style"))
