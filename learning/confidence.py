"""Confidence scoring
===================
Turns "one extraction from one source" into a 0-1 confidence number for
a fact, and updates that number as more sources corroborate it (or as
time passes with nothing re-confirming it). Used by
learning/knowledge_extractor.py when a fact is first added, and again
whenever the same fact turns up from a different source.

Deliberately simple, explainable math (not a learned model) - the
important behavioural properties, not the exact weights, are what
matter:
- a single low-trust source never produces a "high" fact on its own
- independent corroboration matters, but with diminishing returns -
  the 5th confirming source moves the needle less than the 2nd
- old, never-reconfirmed facts drift down rather than staying "high"
  forever, but never decay all the way to "definitely false"
"""

import time

EXTRACTION_WEIGHT = 0.3
SOURCE_WEIGHT = 0.5
CORROBORATION_WEIGHT = 0.2

HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.45

SECONDS_PER_DAY = 86400
DECAY_HALF_LIFE_DAYS = 180
DECAY_FLOOR = 0.2  # decay erodes toward "unconfirmed lately", not "false"


def score(extraction_confidence: float, source_trust: float, corroborating_sources: int = 1) -> float:
    """Combine extraction certainty, source trust, and corroboration count
    into a single 0-1 confidence score for a newly-added fact."""
    extraction_confidence = _clamp(extraction_confidence)
    source_trust = _clamp(source_trust)
    corroborating_sources = max(1, corroborating_sources)
    # each additional independent source adds less than the last:
    # 1 source -> 0, 2 -> 0.5, 3 -> 0.67, 4 -> 0.75, ... of the weight
    corroboration_term = 1 - (1 / corroborating_sources)
    raw = (
        EXTRACTION_WEIGHT * extraction_confidence
        + SOURCE_WEIGHT * source_trust
        + CORROBORATION_WEIGHT * corroboration_term
    )
    return round(_clamp(raw), 4)


def classify(confidence_score: float) -> str:
    """Map a numeric score to a human label used in summaries/UIs."""
    if confidence_score >= HIGH_THRESHOLD:
        return "high"
    if confidence_score >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def corroborate(existing_confidence: float, existing_source_count: int, new_source_trust: float) -> float:
    """A new, independent source has confirmed an existing fact - fold it
    in. More corroborating sources raise the floor; a low-trust
    corroborator barely moves a fact that's already well-supported, but
    a fact can never go DOWN just because a new source agreed with it."""
    new_count = max(1, existing_source_count) + 1
    corroboration_term = 1 - (1 / new_count)
    bump = CORROBORATION_WEIGHT * corroboration_term + 0.1 * _clamp(new_source_trust)
    candidate = existing_confidence * 0.85 + bump
    return round(_clamp(max(existing_confidence, candidate)), 4)


def apply_time_decay(confidence_score: float, last_confirmed_at: float, now: float = None) -> float:
    """Facts nobody has re-confirmed in a long time slowly lose confidence
    (exponential half-life decay toward DECAY_FLOOR, never below it) -
    reflecting that the world, and Ultron's sources, may have moved on."""
    now = now if now is not None else time.time()
    age_days = max(0.0, (now - last_confirmed_at) / SECONDS_PER_DAY)
    if age_days <= 0:
        return round(_clamp(confidence_score), 4)
    decay_factor = 0.5 ** (age_days / DECAY_HALF_LIFE_DAYS)
    decayed = DECAY_FLOOR + (confidence_score - DECAY_FLOOR) * decay_factor
    return round(_clamp(decayed), 4)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))
