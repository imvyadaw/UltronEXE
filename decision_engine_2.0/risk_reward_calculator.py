"""
Risk/reward calculator
=========================
Simple, transparent risk/reward math for a single decision - NOT a
financial-advice engine (no market data, no portfolio optimization).
Three independent, stdlib-only calculations a person can sanity-check
by hand:

  - expected_value(): probability-weighted average outcome across a
    set of scenarios.
  - risk_reward_ratio(): potential_loss vs potential_gain, the plain
    "is this bet worth it" number traders/gamblers use informally.
  - kelly_fraction(): the (capped) Kelly criterion fraction of a
    bankroll to risk, given a win probability and win/loss multiples -
    returned capped at kelly_cap (default 0.25, "quarter Kelly") since
    full Kelly is famously too aggressive for a single heuristic
    number to hand someone without more context.

See decision_engine_2.0's __init__.py for why this file is loaded via
importlib rather than a normal package import.
"""

from typing import Dict, List


def expected_value(scenarios: List[Dict]) -> Dict:
    """scenarios: [{"outcome": float, "probability": float}, ...] -
    probabilities need not sum to exactly 1 (normalized internally),
    but must be non-negative and sum to > 0."""
    if not scenarios:
        return {"success": False, "expected_value": 0.0, "error": "at least one scenario is required"}

    total_prob = sum(max(0.0, s.get("probability", 0.0)) for s in scenarios)
    if total_prob <= 0:
        return {"success": False, "expected_value": 0.0, "error": "probabilities must sum to a positive number"}

    ev = sum(s.get("outcome", 0.0) * (max(0.0, s.get("probability", 0.0)) / total_prob) for s in scenarios)
    return {"success": True, "expected_value": round(ev, 4), "scenario_count": len(scenarios)}


def risk_reward_ratio(potential_loss: float, potential_gain: float) -> Dict:
    """Plain ratio (not probability-weighted) - potential_gain divided
    by potential_loss, both expected as positive magnitudes (e.g. "I
    could lose 200" -> potential_loss=200, not -200). A ratio >= 2 is
    the common informal "worth considering" heuristic threshold, but
    that's just a label attached here for readability, not a rule
    this function enforces."""
    loss = abs(potential_loss)
    gain = abs(potential_gain)
    if loss == 0:
        return {"success": False, "ratio": None, "error": "potential_loss must be non-zero"}

    ratio = round(gain / loss, 4)
    if ratio >= 3:
        label = "strongly favorable"
    elif ratio >= 2:
        label = "favorable"
    elif ratio >= 1:
        label = "roughly balanced"
    else:
        label = "unfavorable"
    return {"success": True, "ratio": ratio, "potential_loss": loss, "potential_gain": gain, "label": label}


def kelly_fraction(
    win_probability: float, win_multiple: float, loss_multiple: float = 1.0, kelly_cap: float = 0.25
) -> Dict:
    """Classic Kelly formula f* = p - (1-p)/b, where b = win_multiple /
    loss_multiple (net odds received on the wager). Returns 0 (not an
    error) if the edge is negative - Kelly says "don't bet", which is
    a valid, meaningful answer, not a failure case. Result is capped
    at kelly_cap and never returned negative."""
    if not (0 < win_probability < 1):
        return {"success": False, "fraction": 0.0, "error": "win_probability must be between 0 and 1 (exclusive)"}
    if win_multiple <= 0 or loss_multiple <= 0:
        return {"success": False, "fraction": 0.0, "error": "win_multiple and loss_multiple must be positive"}

    b = win_multiple / loss_multiple
    raw_f = win_probability - (1 - win_probability) / b
    capped = max(0.0, min(raw_f, kelly_cap))
    return {
        "success": True,
        "raw_fraction": round(raw_f, 4),
        "capped_fraction": round(capped, 4),
        "kelly_cap": kelly_cap,
        "has_positive_edge": raw_f > 0,
    }
