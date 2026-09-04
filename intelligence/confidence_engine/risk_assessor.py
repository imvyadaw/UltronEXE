"""
Risk Assessor (Phase 19.8 - Confidence Engine)
==================================================
Classifies how risky an action is - low/medium/high/critical - from
its name and, when given, its params/context. Deliberately simple/
heuristic, same spirit as entity_extractor.py's keyword matching in
Phase 19.7: a handful of keyword lists cover the obviously-dangerous
and obviously-safe ends, anything unrecognized defaults to "medium"
rather than guessing "low" - an unknown action is exactly the case
where being too permissive is the wrong failure mode. A few context
flags (irreversible, force/recursive params, affecting more than one
item) can bump the base level up, never down.

This module only classifies - it never decides what to do about the
risk (decision_gate.py's job) or how confident we are in the action
itself (confidence_calculator.py's job). Stateless: no persistence,
same as relation_mapper.py in Phase 19.7.
"""

import threading
from typing import Dict, List, Optional

_instance: Optional["RiskAssessor"] = None
_instance_lock = threading.Lock()

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"

_BASE_SCORE = {RISK_LOW: 0.15, RISK_MEDIUM: 0.4, RISK_HIGH: 0.7, RISK_CRITICAL: 0.95}
_LEVEL_ORDER = [RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL]

_CRITICAL_KEYWORDS = {
    "format_drive",
    "factory_reset",
    "wipe",
    "wipe_disk",
    "delete_all",
    "drop_table",
    "drop_database",
    "rm_rf",
    "shutdown_system",
    "uninstall_system",
    "transfer_money",
    "delete_account",
    "revoke_access",
    "disable_security",
}
_HIGH_KEYWORDS = {
    "delete_file",
    "delete",
    "overwrite_file",
    "move_file",
    "send_email",
    "send_message",
    "install",
    "uninstall",
    "kill_process",
    "modify_registry",
    "execute_command",
    "run_command",
    "payment",
    "purchase",
    "delete_folder",
    "format",
    "reset_settings",
    "change_password",
}
_MEDIUM_KEYWORDS = {
    "rename_file",
    "create_file",
    "edit_file",
    "write_file",
    "open_app",
    "close_app",
    "change_setting",
    "schedule",
    "set_reminder",
    "create_folder",
    "copy_file",
    "move_window",
}
_LOW_KEYWORDS = {
    "read_file",
    "get_status",
    "query",
    "search",
    "list",
    "list_files",
    "get_info",
    "check",
    "view",
    "show",
    "summarize",
    "get_weather",
    "get_time",
}

# param keys/values that signal irreversibility or a wider blast radius than the base action implies
_ESCALATING_PARAM_FLAGS = {"force", "recursive", "permanent", "irreversible", "all", "confirm_override"}


class RiskAssessor:
    """action_name/params/context -> {"risk_level", "risk_score", "reasons"}."""

    def assess(self, action_name: str, params: Optional[Dict] = None, context: Optional[Dict] = None) -> Dict:
        params = params or {}
        context = context or {}
        reasons: List[str] = []

        level = self._classify_action(action_name, reasons)
        level = self._apply_param_escalation(level, params, reasons)
        level = self._apply_context_escalation(level, context, reasons)

        score = _BASE_SCORE[level]
        return {"risk_level": level, "risk_score": score, "reasons": reasons}

    @staticmethod
    def _classify_action(action_name: str, reasons: List[str]) -> str:
        normalized = (action_name or "").lower().strip()
        for keyword in _CRITICAL_KEYWORDS:
            if keyword in normalized:
                reasons.append(f"action name matched critical keyword '{keyword}'")
                return RISK_CRITICAL
        for keyword in _HIGH_KEYWORDS:
            if keyword in normalized:
                reasons.append(f"action name matched high-risk keyword '{keyword}'")
                return RISK_HIGH
        for keyword in _MEDIUM_KEYWORDS:
            if keyword in normalized:
                reasons.append(f"action name matched medium-risk keyword '{keyword}'")
                return RISK_MEDIUM
        for keyword in _LOW_KEYWORDS:
            if keyword in normalized:
                reasons.append(f"action name matched low-risk keyword '{keyword}'")
                return RISK_LOW
        reasons.append("no keyword match - defaulting to medium as a safe middle ground")
        return RISK_MEDIUM

    @staticmethod
    def _apply_param_escalation(level: str, params: Dict, reasons: List[str]) -> str:
        for key, value in params.items():
            key_lower = str(key).lower()
            if key_lower in _ESCALATING_PARAM_FLAGS and value:
                reasons.append(f"param '{key}={value}' widens blast radius")
                return RiskAssessor._bump(level, reasons)
        return level

    @staticmethod
    def _apply_context_escalation(level: str, context: Dict, reasons: List[str]) -> str:
        if context.get("irreversible"):
            reasons.append("context flagged irreversible")
            level = RiskAssessor._bump(level, reasons)
        affects_count = context.get("affects_count")
        if isinstance(affects_count, (int, float)) and affects_count > 1:
            reasons.append(f"affects {affects_count} items, not just one")
            level = RiskAssessor._bump(level, reasons)
        return level

    @staticmethod
    def _bump(level: str, reasons: List[str]) -> str:
        idx = _LEVEL_ORDER.index(level)
        if idx < len(_LEVEL_ORDER) - 1:
            new_level = _LEVEL_ORDER[idx + 1]
            reasons.append(f"escalated {level} -> {new_level}")
            return new_level
        return level


def get_risk_assessor() -> RiskAssessor:
    """Process-wide RiskAssessor singleton (stateless, shared for consistency)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = RiskAssessor()
    return _instance
