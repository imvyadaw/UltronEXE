"""
Capability Isolation / Fine-Grained Permissions (P1)
=====================================================
core/capability_registry.py already gives every action a coarse
permission_level ("normal" | "elevated" | "destructive"). That answers
"how risky is this action" but not "what KIND of access does it need" -
a tool can be "normal" and still touch the filesystem, the network, a
person's phone number, or shell execution, and a user may want to
allow one of those categories while blocking another regardless of
risk tier (e.g. "never let anything text people on my behalf, but
file writes are fine").

This module adds that second, orthogonal axis - scopes - plus
isolation profiles (named policies over those scopes) that can be
switched without touching capability_registry's permission_level at
all. Purely additive: nothing here changes what capability_registry
or PermissionGate already decide, it can only add an extra denial on
top, never remove one.

Usage:
    from security.capability_isolation import get_capability_isolation
    iso = get_capability_isolation()
    decision = iso.check("send_email", {"to": "x@y.com"})
    if not decision["allowed"]:
        ...

    iso.set_active_profile("guest")          # switch policy
    iso.set_scope_policy("guest", "communication_send", "deny")
"""

import json
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

POLICY_PATH = Path(__file__).resolve().parent / "capability_policy.json"

# -- scope taxonomy -----------------------------------------------------
SCOPES = (
    "filesystem_read",
    "filesystem_write",
    "network",
    "shell_exec",
    "system_control",  # power, processes, registry, admin
    "communication_send",  # email/sms/whatsapp/telegram/call sends
    "automation_ui",  # mouse/keyboard/window automation
    "media_control",
    "financial",
    "unknown",
)

# Explicit overrides for tools whose name alone is ambiguous or where
# getting the scope wrong would matter (checked before the heuristic
# below). Extend this as real gaps are found in practice - it's meant
# to grow, not to be exhaustive on day one.
TOOL_SCOPE_OVERRIDES: Dict[str, List[str]] = {
    "run_command": ["shell_exec", "system_control"],
    "run_powershell": ["shell_exec", "system_control"],
    "shutdown_pc": ["system_control"],
    "restart_pc": ["system_control"],
    "sign_out": ["system_control"],
    "relaunch_as_admin": ["system_control"],
    "kill_process": ["system_control"],
    "stop_service": ["system_control"],
    "call_phone": ["communication_send"],
    "delete_file": ["filesystem_write"],
    "delete_folder": ["filesystem_write"],
    "clear_downloads": ["filesystem_write"],
    "read_file": ["filesystem_read"],
    "list_directory": ["filesystem_read"],
    "search_files": ["filesystem_read"],
}

# Heuristic keyword -> scope fallback for the hundreds of tools that
# don't have an explicit override - matched against the tool name.
_KEYWORD_SCOPES = (
    (re.compile(r"delete|remove|write|save|create_file|move_file|rename"), "filesystem_write"),
    (re.compile(r"read_file|list_directory|find_folder|search_files|get_file_info"), "filesystem_read"),
    (re.compile(r"http|fetch|download|browse|scrape|search_internet|url|api"), "network"),
    (re.compile(r"run_command|run_powershell|shell|exec_"), "shell_exec"),
    (re.compile(r"shutdown|restart|kill_process|stop_service|admin|registry|startup_program"), "system_control"),
    (re.compile(r"email|sms|whatsapp|telegram|call_phone|send_message|social_post"), "communication_send"),
    (re.compile(r"click|type_text|mouse|keyboard|window|ui_element|macro"), "automation_ui"),
    (re.compile(r"play|pause_media|volume|media|music"), "media_control"),
    (re.compile(r"payment|purchase|transfer_funds|bank|invoice"), "financial"),
)

DEFAULT_PROFILES: Dict[str, Dict[str, str]] = {
    # mode is one of "allow" | "ask" | "deny"
    "default": {scope: "allow" for scope in SCOPES},
    "guest": {
        **{scope: "allow" for scope in SCOPES},
        "shell_exec": "deny",
        "system_control": "deny",
        "communication_send": "ask",
        "financial": "deny",
    },
    "locked_down": {scope: "deny" for scope in SCOPES if scope not in ("filesystem_read",)},
}
DEFAULT_PROFILES["locked_down"]["filesystem_read"] = "allow"


class CapabilityIsolation:
    def __init__(self, policy_path: Path = POLICY_PATH):
        self._policy_path = policy_path
        self._lock = threading.Lock()
        self._profiles: Dict[str, Dict[str, str]] = {}
        self._active_profile = "default"
        self._load()

    # -- persistence ------------------------------------------------------
    def _load(self):
        if self._policy_path.exists():
            try:
                data = json.loads(self._policy_path.read_text())
                self._profiles = data.get("profiles", {})
                self._active_profile = data.get("active_profile", "default")
            except (json.JSONDecodeError, OSError):
                self._profiles = {}
        if not self._profiles:
            self._profiles = {k: dict(v) for k, v in DEFAULT_PROFILES.items()}
            self._save()

    def _save(self):
        self._policy_path.parent.mkdir(parents=True, exist_ok=True)
        self._policy_path.write_text(
            json.dumps({"active_profile": self._active_profile, "profiles": self._profiles}, indent=2)
        )

    # -- scope classification ----------------------------------------------
    def get_scopes(self, tool_name: str) -> List[str]:
        if tool_name in TOOL_SCOPE_OVERRIDES:
            return TOOL_SCOPE_OVERRIDES[tool_name]
        matched = [scope for pattern, scope in _KEYWORD_SCOPES if pattern.search(tool_name)]
        return matched or ["unknown"]

    # -- policy management --------------------------------------------------
    def list_profiles(self) -> List[str]:
        return list(self._profiles.keys())

    def get_active_profile(self) -> str:
        return self._active_profile

    def set_active_profile(self, profile: str) -> bool:
        if profile not in self._profiles:
            return False
        with self._lock:
            self._active_profile = profile
            self._save()
        return True

    def get_policy(self, profile: Optional[str] = None) -> Dict[str, str]:
        return dict(self._profiles.get(profile or self._active_profile, {}))

    def set_scope_policy(self, profile: str, scope: str, mode: str) -> bool:
        if mode not in ("allow", "ask", "deny") or scope not in SCOPES:
            return False
        with self._lock:
            self._profiles.setdefault(profile, dict(DEFAULT_PROFILES["default"]))[scope] = mode
            self._save()
        return True

    # -- the actual gate --------------------------------------------------
    def check(self, tool_name: str, arguments: Optional[Dict] = None, profile: Optional[str] = None) -> Dict:
        """Returns {"allowed": bool, "mode": "allow"|"ask"|"deny", "scopes": [...],
        "reason": str}. 'ask' means: not auto-denied, but the caller should
        require an explicit confirm=true the same way PermissionGate's
        destructive tools already do - it is NOT the same as allowed=True."""
        arguments = arguments or {}
        scopes = self.get_scopes(tool_name)
        policy = self.get_policy(profile)
        # Most restrictive scope wins: if any scope on this tool is denied,
        # the whole call is denied even if another scope would allow it.
        modes = [policy.get(scope, "allow") for scope in scopes]
        if "deny" in modes:
            return {
                "allowed": False,
                "mode": "deny",
                "scopes": scopes,
                "reason": f"scope(s) {[s for s, m in zip(scopes, modes) if m == 'deny']} denied by profile '{self._active_profile}'",
            }
        if "ask" in modes and not arguments.get("confirm"):
            return {
                "allowed": False,
                "mode": "ask",
                "scopes": scopes,
                "reason": f"scope(s) {[s for s, m in zip(scopes, modes) if m == 'ask']} require confirm=true under profile '{self._active_profile}'",
            }
        return {"allowed": True, "mode": "allow", "scopes": scopes, "reason": ""}


_instance: Optional[CapabilityIsolation] = None
_instance_lock = threading.Lock()


def get_capability_isolation() -> CapabilityIsolation:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CapabilityIsolation()
    return _instance
