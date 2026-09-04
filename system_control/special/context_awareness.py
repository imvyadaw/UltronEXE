"""Context Awareness Control
=============================
Aggregates the raw signals that already exist in three separate
places - proactive.monitors.user_activity (foreground window, idle
time), proactive.monitors.system_health (battery/CPU), and
proactive.monitors.network_status (connectivity) - into one
"what is happening right now" snapshot, and layers cognitive_core's
context_bridge.CognitiveContextBridge (the AI-facing goal/tool-history
context) on top for the conversational half. None of those modules
know about each other; this is the join.

On top of the snapshot, this owns simple IF-context-THEN-system-action
rules (e.g. "when the foreground window matches a meeting app, mute
the mic") stored as JSON. Creating, editing, or enabling a rule is
confirm-gated since an active rule fires system actions unattended.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

_RULES_PATH = Path(__file__).resolve().parent / "_context_rules.json"


class ContextAwarenessControl:
    def get_snapshot(self) -> Dict:
        snapshot: Dict = {}
        try:
            from proactive.monitors.user_activity import get_user_activity_monitor

            snapshot["activity"] = get_user_activity_monitor().snapshot()
        except Exception as e:
            snapshot["activity"] = {"error": str(e)}
        try:
            from proactive.monitors.system_health import get_system_health_monitor

            snapshot["system_health"] = get_system_health_monitor().snapshot()
        except Exception as e:
            snapshot["system_health"] = {"error": str(e)}
        try:
            from proactive.monitors.network_status import get_network_status_monitor

            snapshot["network"] = get_network_status_monitor().snapshot()
        except Exception as e:
            snapshot["network"] = {"error": str(e)}
        try:
            from cognitive_core.context_bridge import get_context_bridge

            snapshot["cognitive"] = get_context_bridge().snapshot()
        except Exception as e:
            snapshot["cognitive"] = {"error": str(e)}
        return snapshot

    def _load_rules(self) -> List[Dict]:
        if _RULES_PATH.exists():
            try:
                return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_rules(self, rules: List[Dict]) -> None:
        _RULES_PATH.write_text(json.dumps(rules, indent=2), encoding="utf-8")

    def list_rules(self) -> Dict:
        return {"rules": self._load_rules()}

    def add_rule(
        self, name: str, window_title_pattern: str, action: str, enabled: bool = True, confirm: bool = False
    ) -> Dict:
        """action is one of: 'mute_mic', 'unmute_mic', 'do_not_disturb_on',
        'do_not_disturb_off' - kept small on purpose; wire more via
        system_control.hardware.microphone_control / ui.notification_manager
        as needed rather than growing this into a generic scripting engine."""
        allowed_actions = {"mute_mic", "unmute_mic", "do_not_disturb_on", "do_not_disturb_off"}
        if action not in allowed_actions:
            return {"error": f"action must be one of {sorted(allowed_actions)}"}
        try:
            re.compile(window_title_pattern)
        except re.error as e:
            return {"error": f"invalid regex: {e}"}
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will create rule '{name}': when the foreground window matches /{window_title_pattern}/, run '{action}'.",
            }
        rules = self._load_rules()
        rules = [r for r in rules if r.get("name") != name]
        rules.append({"name": name, "pattern": window_title_pattern, "action": action, "enabled": enabled})
        self._save_rules(rules)
        return {
            "success": True,
            "rule": {"name": name, "pattern": window_title_pattern, "action": action, "enabled": enabled},
        }

    def remove_rule(self, name: str, confirm: bool = False) -> Dict:
        if not confirm:
            return {"requires_confirmation": True, "preview": f"This will remove context rule '{name}'."}
        rules = [r for r in self._load_rules() if r.get("name") != name]
        self._save_rules(rules)
        return {"success": True, "removed": name}

    def set_rule_enabled(self, name: str, enabled: bool, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will {'enable' if enabled else 'disable'} context rule '{name}'.",
            }
        rules = self._load_rules()
        found = False
        for r in rules:
            if r.get("name") == name:
                r["enabled"] = enabled
                found = True
        if not found:
            return {"error": f"No rule named '{name}'."}
        self._save_rules(rules)
        return {"success": True, "name": name, "enabled": enabled}

    def evaluate_and_apply(self) -> Dict:
        """Check current foreground window against enabled rules and fire
        the first match's action. Actual mic/DND control is delegated."""
        try:
            from proactive.monitors.user_activity import get_user_activity_monitor

            title = get_user_activity_monitor().active_window_title() or ""
        except Exception as e:
            return {"error": str(e)}
        for rule in self._load_rules():
            if not rule.get("enabled", True):
                continue
            if re.search(rule.get("pattern", ""), title, re.IGNORECASE):
                result = self._apply_action(rule["action"])
                return {"matched_rule": rule["name"], "window_title": title, "result": result}
        return {"matched_rule": None, "window_title": title}

    def _apply_action(self, action: str) -> Dict:
        try:
            if action in ("mute_mic", "unmute_mic"):
                from system_control.hardware.microphone_control import MicrophoneControl

                return MicrophoneControl().set_mic_mute(action == "mute_mic")
            if action in ("do_not_disturb_on", "do_not_disturb_off"):
                from system_control.ui.notification_manager import NotificationManager

                mode = "priority_only" if action == "do_not_disturb_on" else "off"
                return NotificationManager().set_focus_assist_mode(mode, confirm=True)
        except Exception as e:
            return {"error": str(e)}
        return {"error": f"No handler for action '{action}'"}


_instance: Optional[ContextAwarenessControl] = None


def get_context_awareness_control() -> ContextAwarenessControl:
    global _instance
    if _instance is None:
        _instance = ContextAwarenessControl()
    return _instance
