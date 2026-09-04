"""Safety policy
=============
Pure classification, no queueing and no side effects on skill_builder -
that split stays with review_queue.py, same reasoning learning/confidence.py
(pure scoring) is kept separate from learning/source_validator.py
(persisted trust tiers) and learning/forgetting.py (the thing that
actually acts on a score).

classify() runs a keyword heuristic - same "fast first pass, not a
guarantee" spirit as source_validator.py's domain heuristics - over a
procedure's name plus its steps' tool/argument text, against four risk
categories that have nothing to do with how *reliable* a procedure is
(that's memory/procedural/'s success_rate) and everything to do with
how expensive a mistake would be: destructive, financial,
outbound_communication, system_security. Any match means TIER_REVIEW;
no match means TIER_AUTO.

The heuristic will get some calls wrong in both directions - a
false-positive on a procedure named "delete_my_todo_item", a
false-negative on something risky worded around the keyword list.
set_override()/clear_override() is the manual escape hatch for either
case, persisted per procedure name (storage/safety/policy_overrides.json)
so a human's correction sticks without needing to touch the keyword
list itself.
"""

import json
from typing import Dict, List, Optional

from config import STORAGE_DIR
from core.logger import get_logger

logger = get_logger("safety.policy")

OVERRIDES_PATH = STORAGE_DIR / "safety" / "policy_overrides.json"

TIER_AUTO = "auto"
TIER_REVIEW = "needs_review"

# Heuristic, not exhaustive. Keyed by category purely for a readable
# `matched` list in the classification result - the categories
# themselves carry no different treatment, any match is TIER_REVIEW.
RISK_KEYWORDS = {
    "destructive": [
        "delete",
        "remove",
        "uninstall",
        "format",
        "wipe",
        "erase",
        "kill",
        "terminate",
        "drop_table",
        "rm ",
        "factory_reset",
    ],
    "financial": [
        "pay",
        "purchase",
        "buy",
        "checkout",
        "transfer_funds",
        "invoice",
        "bank",
        "wire_transfer",
        "subscribe",
        "charge_card",
    ],
    "outbound_communication": [
        "send_email",
        "send_message",
        "post_to",
        "publish",
        "tweet",
        "reply_to",
        "send_sms",
        "broadcast",
    ],
    "system_security": [
        "sudo",
        "chmod",
        "chown",
        "firewall",
        "password",
        "credential",
        "api_key",
        "private_key",
        "disable_antivirus",
        "registry_edit",
    ],
}


class SafetyPolicy:
    """Classifies a procedure/skill as auto-promotable or human-review-required, from its name + step content."""

    def __init__(self):
        self._overrides = self._load_overrides()

    def classify(self, name: str, steps: Optional[List[Dict]] = None) -> Dict:
        """`steps` is the same shape skill_learner.py already builds -
        [{"tool": ..., "arguments": ...}, ...] - so callers can pass a
        procedure's stored steps straight through."""
        try:
            override = self._overrides.get(name)
            if override is not None:
                return {
                    "name": name,
                    "tier": override["tier"],
                    "reason": "manual_override",
                    "matched": [],
                }
            text = self._searchable_text(name, steps)
            matched = [category for category, keywords in RISK_KEYWORDS.items() if any(kw in text for kw in keywords)]
            tier = TIER_REVIEW if matched else TIER_AUTO
            return {
                "name": name,
                "tier": tier,
                "reason": "keyword_match" if matched else "no_risk_keywords",
                "matched": matched,
            }
        except Exception as e:
            logger.error(f"classify() failed for '{name}': {e}")
            # Fail closed - an error classifying is not the same as a
            # clean bill of health, so default to review rather than auto.
            return {"name": name, "tier": TIER_REVIEW, "reason": f"classification_error: {e}", "matched": []}

    def set_override(self, name: str, tier: str, reason: str = "") -> Dict:
        if tier not in (TIER_AUTO, TIER_REVIEW):
            return {"error": f"tier must be '{TIER_AUTO}' or '{TIER_REVIEW}'"}
        self._overrides[name] = {"tier": tier, "reason": reason}
        self._save_overrides()
        logger.info(f"Safety override set: '{name}' -> {tier} ({reason})")
        return {"success": True, "name": name, "tier": tier}

    def clear_override(self, name: str) -> Dict:
        if name not in self._overrides:
            return {"error": f"No override for '{name}'"}
        del self._overrides[name]
        self._save_overrides()
        logger.info(f"Safety override cleared: '{name}'")
        return {"success": True, "name": name}

    def list_overrides(self) -> Dict:
        return {"count": len(self._overrides), "overrides": dict(self._overrides)}

    @staticmethod
    def _searchable_text(name: str, steps: Optional[List[Dict]]) -> str:
        parts = [name]
        for s in steps or []:
            parts.append(str(s.get("tool", "")))
            args = s.get("arguments", s.get("detail", ""))
            parts.append(args if isinstance(args, str) else json.dumps(args, default=str))
        return " ".join(parts).lower()

    # -- persistence -----------------------------------------------------
    def _load_overrides(self) -> Dict:
        if not OVERRIDES_PATH.exists():
            return {}
        try:
            return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load safety overrides ({e}), starting fresh")
            return {}

    def _save_overrides(self) -> None:
        OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        OVERRIDES_PATH.write_text(json.dumps(self._overrides, indent=2, ensure_ascii=False), encoding="utf-8")


_safety_policy: Optional[SafetyPolicy] = None


def get_safety_policy() -> SafetyPolicy:
    global _safety_policy
    if _safety_policy is None:
        _safety_policy = SafetyPolicy()
    return _safety_policy
