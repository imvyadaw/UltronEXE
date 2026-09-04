"""
Control Panel
=============
Every module in Phase 18 so far is a read path (dashboard, history),
a write path with no single caller (personality.adjust, forget.*), or
a decision path already owned by decision_maker.py. control_panel.py
is the one place that ties all of Phase 18's mutating, user-facing
operations behind a single dispatcher - the same "front door" role
brain.py plays for conversation, applied to management instead. It
doesn't duplicate any logic; every method here is a thin, named
wrapper around a call that already exists elsewhere, kept together so
a debug console, a future UI, or a voice command like "forget the
office" has exactly one class to import instead of five.

execute() exists for the voice/text-command case specifically - a
small fixed vocabulary (not an LLM call, matching decision_maker's own
preference for cheap heuristics over an extra round-trip for something
this bounded) mapped to the methods below. Anything not matching the
vocabulary returns an "unrecognized" result rather than guessing.
"""

from typing import Dict, List, Optional


class ControlPanel:
    """Single dispatcher for Phase 18's status + management operations.
    Use get_control_panel()."""

    # -- status --------------------------------------------------------
    def status(self) -> Dict:
        from command.dashboard import get_dashboard

        return get_dashboard().snapshot()

    def recent_activity(self, limit: int = 20, kinds: Optional[List[str]] = None) -> List[Dict]:
        from command.history import get_history

        return get_history().timeline(limit=limit, kinds=kinds)

    def report(self, period: str = "daily") -> Dict:
        from command.reports import get_report_generator

        gen = get_report_generator()
        return gen.weekly_report() if period == "weekly" else gen.daily_report()

    # -- personality -----------------------------------------------------
    def adjust_trait(self, trait: str, delta: float, reason: str = "") -> Dict:
        from core.personality import get_personality

        return get_personality().adjust(trait, delta, reason=reason)

    # -- forgetting --------------------------------------------------------
    def forget_person(self, name: str) -> Dict:
        from memory.forget import get_forgetter

        return get_forgetter().forget_person(name)

    def forget_place(self, name: str) -> Dict:
        from memory.forget import get_forgetter

        return get_forgetter().forget_place(name)

    def forget_habit(self, action: str) -> Dict:
        from memory.forget import get_forgetter

        return get_forgetter().forget_habit(action)

    def forget_fact(self, subject: str, predicate: Optional[str] = None) -> Dict:
        from memory.forget import get_forgetter

        return get_forgetter().forget_fact(subject, predicate)

    def forget_everything(self, confirm: bool = False) -> Dict:
        from memory.forget import get_forgetter

        return get_forgetter().forget_everything(confirm=confirm)

    # -- small fixed-vocabulary command dispatcher ------------------------
    def execute(self, command: str) -> Dict:
        """Handles a short list of admin phrases directly, case-
        insensitive, e.g.:
            "status" / "dashboard"        -> status()
            "history" / "recent activity" -> recent_activity()
            "daily report"                -> report("daily")
            "weekly report"               -> report("weekly")
            "forget person <name>"        -> forget_person(name)
            "forget place <name>"         -> forget_place(name)
            "forget habit <action>"       -> forget_habit(action)
        Anything else returns {"error": "unrecognized command", ...}
        rather than guessing - the same "ask, don't guess" instinct
        decision_maker.py applies to low-confidence goals."""
        normalized = command.strip().lower()

        if normalized in ("status", "dashboard"):
            return {"result": self.status()}
        if normalized in ("history", "recent activity"):
            return {"result": self.recent_activity()}
        if normalized == "daily report":
            return {"result": self.report("daily")}
        if normalized == "weekly report":
            return {"result": self.report("weekly")}
        if normalized.startswith("forget person "):
            return {"result": self.forget_person(command[len("forget person ") :].strip())}
        if normalized.startswith("forget place "):
            return {"result": self.forget_place(command[len("forget place ") :].strip())}
        if normalized.startswith("forget habit "):
            return {"result": self.forget_habit(command[len("forget habit ") :].strip())}

        return {"error": "unrecognized command", "command": command}


_control_panel: Optional[ControlPanel] = None


def get_control_panel() -> ControlPanel:
    global _control_panel
    if _control_panel is None:
        _control_panel = ControlPanel()
    return _control_panel
