"""
Multi-criteria decision (weighted-sum MCDA)
==============================================
Standard weighted-sum multi-criteria decision analysis: given several
options, each scored on several named criteria, and a weight per
criterion, compute one ranked "best option" instead of the user
mentally juggling a spreadsheet.

Deliberately dependency-free (pure stdlib, no numpy) - the whole
computation is a handful of multiplications, and this is meant to be
callable standalone from a tool-call handler without importing a
heavier project subsystem for it. See this package's __init__.py for
why this file has to be loaded via importlib rather than a normal
import.

Score normalization: each criterion's raw scores across all options
are min-max normalized to 0-1 BEFORE weighting, so criteria on wildly
different scales (e.g. "price in rupees" vs "rating out of 5") don't
silently dominate just because their raw numbers are bigger. A
criterion marked lower_is_better=True (e.g. price, risk) is inverted
after normalization so higher-normalized-score always means "better"
for every criterion, letting the final weighted sum be a plain sum.
"""

from typing import Dict, List


def _normalize(values: List[float], lower_is_better: bool) -> List[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]  # all options tie on this criterion
    normed = [(v - lo) / (hi - lo) for v in values]
    return [1.0 - n for n in normed] if lower_is_better else normed


def evaluate(options: List[Dict], criteria: Dict[str, Dict]) -> Dict:
    """
    options: [{"name": str, "scores": {criterion_name: raw_value, ...}}, ...]
    criteria: {criterion_name: {"weight": float, "lower_is_better": bool}}
              weights need not sum to 1 - they're normalized internally.

    Returns:
        {
          "success": bool,
          "ranked": [{"name": str, "weighted_score": float, "breakdown": {...}}, ...],
          "best": {...} | None,
        }
    """
    if not options or not criteria:
        return {"success": False, "ranked": [], "best": None, "error": "options and criteria are both required"}

    total_weight = sum(c.get("weight", 0) for c in criteria.values())
    if total_weight <= 0:
        return {"success": False, "ranked": [], "best": None, "error": "criteria weights must sum to a positive number"}

    normalized: Dict[str, List[float]] = {}
    for crit_name, crit_def in criteria.items():
        raw_values = [opt.get("scores", {}).get(crit_name, 0.0) for opt in options]
        normalized[crit_name] = _normalize(raw_values, bool(crit_def.get("lower_is_better", False)))

    ranked = []
    for idx, opt in enumerate(options):
        breakdown = {}
        weighted_total = 0.0
        for crit_name, crit_def in criteria.items():
            weight_share = crit_def.get("weight", 0) / total_weight
            norm_score = normalized[crit_name][idx]
            contribution = norm_score * weight_share
            breakdown[crit_name] = {
                "raw": opt.get("scores", {}).get(crit_name, 0.0),
                "normalized": round(norm_score, 4),
                "weight_share": round(weight_share, 4),
                "contribution": round(contribution, 4),
            }
            weighted_total += contribution
        ranked.append(
            {
                "name": opt.get("name", f"option_{idx + 1}"),
                "weighted_score": round(weighted_total, 4),
                "breakdown": breakdown,
            }
        )

    ranked.sort(key=lambda r: r["weighted_score"], reverse=True)
    return {"success": True, "ranked": ranked, "best": ranked[0] if ranked else None}
