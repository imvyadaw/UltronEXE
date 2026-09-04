"""
user_adaptation.py
=====================
Tracks slowly-changing user preferences - preferred verbosity,
formality, language mix (e.g. Hinglish vs. English), confirmation
style ("always ask before deleting" vs "just do it"), wake-word
sensitivity - and exposes them as a single settled profile the rest
of ULTRON can read. Preferences update via an exponential moving
average so one unusual interaction doesn't swing behavior wildly;
they settle in gradually as a pattern repeats.

Explicit user settings (from a settings UI/voice command) always
take precedence over inferred ones - `set_explicit()` pins a value
so inference no longer drifts it.

Dependencies: none beyond the standard library.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict

logger = logging.getLogger("ultron.user_adaptation")

DEFAULT_STORE = Path("ultron_data/learning/user_profile.json")

_ALPHA = 0.15  # EMA smoothing factor for inferred numeric preferences


@dataclass
class UserProfile:
    verbosity: float = 0.5  # 0=terse, 1=very detailed
    formality: float = 0.5  # 0=casual, 1=formal
    confirmation_bias: float = 0.5  # 0=just do it, 1=always confirm first
    preferred_language: str = "hinglish"
    explicit_pins: Dict[str, bool] = field(default_factory=dict)


class UserAdaptationEngine:
    """Maintains a slowly-adapting profile of user communication/interaction preferences."""

    def __init__(self, store_path: Path = DEFAULT_STORE):
        self.store_path = Path(store_path)
        self._lock = threading.Lock()
        self.profile = UserProfile()
        self._load()

    def _load(self):
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self.profile = UserProfile(**data)
        except (json.JSONDecodeError, TypeError, OSError) as exc:
            logger.warning("Could not load user profile (%s), using defaults", exc)

    def _save(self):
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.profile), indent=2), encoding="utf-8")
        tmp.replace(self.store_path)

    def observe(self, field_name: str, observed_value: float):
        """
        Nudge a numeric preference (verbosity/formality/confirmation_bias)
        toward an observed data point via EMA, unless it's been explicitly
        pinned by the user.
        """
        if field_name not in ("verbosity", "formality", "confirmation_bias"):
            raise ValueError(f"Unknown adaptive field: {field_name}")
        with self._lock:
            if self.profile.explicit_pins.get(field_name):
                logger.debug("Skipping inference for '%s' - explicitly pinned by user", field_name)
                return
            current = getattr(self.profile, field_name)
            updated = current + _ALPHA * (max(0.0, min(1.0, observed_value)) - current)
            setattr(self.profile, field_name, round(updated, 3))
            self._save()
        logger.debug("Adapted '%s' -> %.3f", field_name, updated)

    def set_explicit(self, field_name: str, value):
        """User (or a settings command) explicitly sets a preference; pins it against further drift."""
        with self._lock:
            setattr(self.profile, field_name, value)
            if field_name in ("verbosity", "formality", "confirmation_bias"):
                self.profile.explicit_pins[field_name] = True
            self._save()
        logger.info("Explicit preference set: %s = %s", field_name, value)

    def get_profile(self) -> UserProfile:
        return self.profile


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = UserAdaptationEngine(store_path=Path("ultron_data/learning/_demo_user_profile.json"))
    engine.observe("verbosity", 0.9)  # user asked a long, detail-seeking follow-up
    engine.observe("verbosity", 0.85)
    print(engine.get_profile())
