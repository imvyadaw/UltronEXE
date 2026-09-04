"""Multi User Profiles Control
===============================
Links two things that already exist separately: Windows OS accounts
(managed by system_control.security.user_accounts.UserAccountsManager
- create/remove/enable/admin/password, this module does NOT re-wrap
that CRUD) and ULTRON's own per-user trait model
(memory.user.user_model.UserModel - preferences/personality, one
process-wide singleton with no notion of "which Windows user is this
for"). This module owns the mapping between the two (stored as JSON,
keyed by Windows username) and the "active profile" switch that other
ULTRON code should read to know whose UserModel data to use, since
UserModel itself has no concept of multiple profiles.

Linking a Windows account to a profile, or switching the active
profile, is confirm-gated since it changes which stored
preferences/personality ULTRON acts on next.
"""
import logging

import json
from pathlib import Path
from typing import Dict, Optional

_LINKS_PATH = Path(__file__).resolve().parent / "_profile_links.json"
_ACTIVE_PATH = Path(__file__).resolve().parent / "_active_profile.json"


class MultiUserProfilesControl:
    def _load_links(self) -> Dict:
        if _LINKS_PATH.exists():
            try:
                return json.loads(_LINKS_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_links(self, links: Dict) -> None:
        _LINKS_PATH.write_text(json.dumps(links, indent=2), encoding="utf-8")

    def list_os_accounts(self) -> Dict:
        from system_control.security.user_accounts import UserAccountsManager

        return UserAccountsManager().list_accounts()

    def link_account_to_profile(self, windows_username: str, profile_id: str, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will link Windows account '{windows_username}' to ULTRON profile '{profile_id}'.",
            }
        links = self._load_links()
        links[windows_username] = profile_id
        self._save_links(links)
        return {"success": True, "windows_username": windows_username, "profile_id": profile_id}

    def unlink_account(self, windows_username: str, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will unlink Windows account '{windows_username}' from any ULTRON profile.",
            }
        links = self._load_links()
        removed = links.pop(windows_username, None)
        self._save_links(links)
        return {"success": True, "removed": removed}

    def list_links(self) -> Dict:
        return {"links": self._load_links()}

    def get_active_profile(self) -> Dict:
        if _ACTIVE_PATH.exists():
            try:
                return json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))
            except Exception:
                logging.getLogger(__name__).exception("Suppressed Exception")
        return {"profile_id": None}

    def set_active_profile(self, profile_id: str, confirm: bool = False) -> Dict:
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will switch ULTRON's active profile to '{profile_id}' - future preference/personality reads use this profile's data.",
            }
        _ACTIVE_PATH.write_text(json.dumps({"profile_id": profile_id}), encoding="utf-8")
        return {"success": True, "profile_id": profile_id}

    def activate_profile_for_windows_account(self, windows_username: str, confirm: bool = False) -> Dict:
        """Convenience: look up the linked profile for a Windows account
        (e.g. after a fast-user-switch or face-login match) and make it
        active in one call."""
        profile_id = self._load_links().get(windows_username)
        if not profile_id:
            return {"error": f"No ULTRON profile linked to Windows account '{windows_username}'."}
        return self.set_active_profile(profile_id, confirm=confirm)

    def get_active_profile_traits(self, min_confidence: float = 0.0) -> Dict:
        """Reads memory.user.user_model.UserModel's traits - note that
        model is a single process-wide store, so this reflects whatever
        ULTRON currently has loaded, tagged with which profile is
        nominally active per set_active_profile()."""
        from memory.user.user_model import get_user_model

        return {
            "active_profile": self.get_active_profile().get("profile_id"),
            "traits": get_user_model().all_traits(min_confidence=min_confidence),
        }

    def switch_windows_account(self, windows_username: str, confirm: bool = False) -> Dict:
        """Fast-user-switch to another Windows account (needs the target
        account to already exist - use list_os_accounts() /
        UserAccountsManager to create one first)."""
        if not confirm:
            return {
                "requires_confirmation": True,
                "preview": f"This will fast-switch the active Windows session to '{windows_username}'.",
            }
        import subprocess

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    'tsdiscon; & "$env:windir\\System32\\tscon.exe" /dest:console',
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {
                "success": result.returncode == 0,
                "note": "Triggered a session switch via tscon; full account-targeted switch requires the Windows lock-screen user picker.",
                "stderr": result.stderr.strip(),
            }
        except Exception as e:
            return {"error": str(e)}


_instance: Optional[MultiUserProfilesControl] = None


def get_multi_user_profiles_control() -> MultiUserProfilesControl:
    global _instance
    if _instance is None:
        _instance = MultiUserProfilesControl()
    return _instance
