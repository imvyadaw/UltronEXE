"""Security Control tool registry
===================================
Wires system_control/security/* (Defender, all-registered-AV status,
ransomware/Controlled-Folder-Access, BitLocker, local user accounts,
local password/lockout policy) into the AI tool-calling loop. Same
pattern as ai/network_control_tools.py: lazy singletons + a flat
SECURITY_CONTROL_TOOLS / SECURITY_CONTROL_DIRECT_HANDLERS pair, merged
at the bottom of ai/tools_schema.py and ai/tool_runtime.py respectively
(see the two-line imports there).

Naming: every tool is prefixed `secctl_` to avoid colliding with the
existing `security_*`/vault/voice-lock/face-lock tools elsewhere (those
wire ULTRON's OWN internal auth/encryption layer, not the Windows OS's
security features - see system_control/security/__init__.py's
docstring for the same distinction spelled out at the package level).

Every state-changing method on the underlying classes is confirm-gated
(confirm: bool, defaults False) - same pattern as every other
destructive tool in this codebase. Several of these (disabling
real-time protection, disabling BitLocker, granting admin, adding AV
exclusions) are genuine reductions in this machine's security posture,
so the preview text for those spells out the exposure, not just the
mechanical change.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - see ai/new_skills_tools.py's docstring for why (avoids a
    circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _pick(d: dict, keys: list) -> dict:
    """Filter a raw tool-call args dict down to the keys a method accepts,
    dropping missing/None entries so the method's own defaults apply."""
    return {k: d[k] for k in keys if k in d and d[k] is not None}


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "defender":
        from system_control.security.defender_manager import DefenderManager

        obj = DefenderManager()
    elif key == "antivirus":
        from system_control.security.antivirus_manager import AntivirusManager

        obj = AntivirusManager()
    elif key == "ransomware":
        from system_control.security.ransomware_protection import RansomwareProtection

        obj = RansomwareProtection()
    elif key == "bitlocker":
        from system_control.security.bitlocker_manager import BitLockerManager

        obj = BitLockerManager()
    elif key == "accounts":
        from system_control.security.user_accounts import UserAccountsManager

        obj = UserAccountsManager()
    elif key == "password_policy":
        from system_control.security.password_policy import PasswordPolicy

        obj = PasswordPolicy()
    elif key == "uac":
        from system_control.security.uac_manager import UACManager

        obj = UACManager()
    elif key == "app_permissions":
        from system_control.security.app_permissions import AppPermissionsManager

        obj = AppPermissionsManager()
    elif key == "privacy":
        from system_control.security.privacy_manager import PrivacyManager

        obj = PrivacyManager()
    elif key == "activity_history":
        from system_control.security.activity_history import ActivityHistoryManager

        obj = ActivityHistoryManager()
    elif key == "cookies":
        from system_control.security.cookies_manager import CookiesManager

        obj = CookiesManager()
    elif key == "certificates":
        from system_control.security.certificates_manager import CertificatesManager

        obj = CertificatesManager()
    elif key == "smartscreen":
        from system_control.security.smartscreen_manager import SmartScreenManager

        obj = SmartScreenManager()
    elif key == "exploit_protection":
        from system_control.security.exploit_protection import ExploitProtectionManager

        obj = ExploitProtectionManager()
    else:
        raise KeyError(f"Unknown security_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
SECURITY_CONTROL_TOOLS = [
    # -- DefenderManager --
    _tool(
        "secctl_defender_get_status",
        "Get overall Windows Defender status: real-time protection, signature age, last scan times.",
    ),
    _tool(
        "secctl_defender_set_realtime_protection",
        "Enable or disable Defender real-time protection. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_defender_set_cloud_protection",
        "Enable or disable Defender cloud-delivered protection (MAPS). Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_defender_start_scan",
        "Start a Defender scan ('QuickScan' or 'FullScan'). Confirm-gated.",
        {"scan_type": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    _tool(
        "secctl_defender_update_signatures",
        "Update Defender's virus/spyware definitions.",
    ),
    _tool(
        "secctl_defender_list_threat_history",
        "List recently detected threats from Defender's history.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "secctl_defender_list_exclusions",
        "List current Defender path/process/extension exclusions.",
    ),
    _tool(
        "secctl_defender_add_exclusion_path",
        "Add a folder/file path Defender should skip scanning. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "secctl_defender_remove_exclusion_path",
        "Remove a previously added Defender path exclusion. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    # -- AntivirusManager --
    _tool(
        "secctl_av_list_registered_products",
        "List every antivirus product Windows Security Center knows about (Defender and/or third-party), with enabled/up-to-date state.",
    ),
    _tool(
        "secctl_av_get_active",
        "Return whichever registered AV product(s) are currently enabled and actually protecting this machine.",
    ),
    _tool(
        "secctl_av_is_outdated",
        "Flag any enabled AV product whose signatures are stale.",
    ),
    _tool(
        "secctl_av_open_security_app",
        "Open the Windows Security app to a given page (home, virus, app-browser, account, device, network, family).",
        {"page": {"type": "string"}},
    ),
    # -- RansomwareProtection (Controlled Folder Access) --
    _tool(
        "secctl_ransomware_get_status",
        "Check whether Controlled Folder Access (ransomware protection) is enabled.",
    ),
    _tool(
        "secctl_ransomware_set_enabled",
        "Enable or disable Controlled Folder Access, optionally in audit-only mode. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "audit_mode": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_ransomware_list_protected_folders",
        "List folders currently protected by Controlled Folder Access.",
    ),
    _tool(
        "secctl_ransomware_add_protected_folder",
        "Add a folder to the ransomware-protected list. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "secctl_ransomware_remove_protected_folder",
        "Remove a folder from the ransomware-protected list. Confirm-gated.",
        {"path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["path"],
    ),
    _tool(
        "secctl_ransomware_list_allowed_apps",
        "List apps allowed to bypass Controlled Folder Access for protected folders.",
    ),
    _tool(
        "secctl_ransomware_add_allowed_app",
        "Allow a specific app (by exe path) to bypass Controlled Folder Access. Confirm-gated.",
        {"exe_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["exe_path"],
    ),
    _tool(
        "secctl_ransomware_remove_allowed_app",
        "Revoke a previously allowed app's Controlled Folder Access bypass. Confirm-gated.",
        {"exe_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["exe_path"],
    ),
    # -- BitLockerManager --
    _tool(
        "secctl_bitlocker_list_volumes",
        "List all volumes and their BitLocker protection status.",
    ),
    _tool(
        "secctl_bitlocker_get_status",
        "Get BitLocker status for a single drive letter.",
        {"drive_letter": {"type": "string"}},
        ["drive_letter"],
    ),
    _tool(
        "secctl_bitlocker_enable",
        "Turn on BitLocker encryption for a volume. Confirm-gated, needs admin.",
        {"drive_letter": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    _tool(
        "secctl_bitlocker_disable",
        "Turn off BitLocker and decrypt a volume. Confirm-gated, needs admin.",
        {"drive_letter": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    _tool(
        "secctl_bitlocker_lock_volume",
        "Lock an encrypted, unlocked volume. Confirm-gated, needs admin.",
        {"drive_letter": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    _tool(
        "secctl_bitlocker_unlock_volume",
        "Unlock a locked BitLocker volume using a password or recovery key. Confirm-gated.",
        {
            "drive_letter": {"type": "string"},
            "password": {"type": "string"},
            "recovery_key": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["drive_letter"],
    ),
    _tool(
        "secctl_bitlocker_get_recovery_key",
        "Retrieve the BitLocker recovery key(s) for a volume. Confirm-gated - reveals a drive-decrypting secret.",
        {"drive_letter": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["drive_letter"],
    ),
    # -- UserAccountsManager --
    _tool(
        "secctl_accounts_list",
        "List local Windows user accounts with enabled/admin status.",
    ),
    _tool(
        "secctl_accounts_get_status",
        "Get status for a single local account by username.",
        {"username": {"type": "string"}},
        ["username"],
    ),
    _tool(
        "secctl_accounts_create",
        "Create a new local user account, optionally as Administrator. Confirm-gated, needs admin.",
        {
            "username": {"type": "string"},
            "password": {"type": "string"},
            "make_admin": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["username", "password"],
    ),
    _tool(
        "secctl_accounts_remove",
        "Delete a local user account. Confirm-gated, needs admin.",
        {"username": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["username"],
    ),
    _tool(
        "secctl_accounts_set_enabled",
        "Enable or disable a local account's ability to log in. Confirm-gated, needs admin.",
        {"username": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["username", "enabled"],
    ),
    _tool(
        "secctl_accounts_set_admin",
        "Grant or revoke Administrator privileges for a local account. Confirm-gated, needs admin.",
        {"username": {"type": "string"}, "is_admin": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["username", "is_admin"],
    ),
    _tool(
        "secctl_accounts_reset_password",
        "Reset a local account's password. Confirm-gated, needs admin.",
        {"username": {"type": "string"}, "new_password": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["username", "new_password"],
    ),
    # -- PasswordPolicy --
    _tool(
        "secctl_pwpolicy_get",
        "Get current local password and account-lockout policy.",
    ),
    _tool(
        "secctl_pwpolicy_set_min_length",
        "Set the minimum required local password length. Confirm-gated, needs admin.",
        {"length": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["length"],
    ),
    _tool(
        "secctl_pwpolicy_set_max_age",
        "Set how many days a local password stays valid (0 = never expires). Confirm-gated, needs admin.",
        {"days": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["days"],
    ),
    _tool(
        "secctl_pwpolicy_set_min_age",
        "Set the minimum days before a local password can be changed again. Confirm-gated, needs admin.",
        {"days": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["days"],
    ),
    _tool(
        "secctl_pwpolicy_set_history",
        "Set how many previous local passwords are remembered to block reuse. Confirm-gated, needs admin.",
        {"count": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["count"],
    ),
    _tool(
        "secctl_pwpolicy_set_lockout",
        "Set account-lockout threshold/duration/observation-window for local accounts. Confirm-gated, needs admin.",
        {
            "threshold": {"type": "integer"},
            "duration_minutes": {"type": "integer"},
            "observation_window_minutes": {"type": "integer"},
            "confirm": {"type": "boolean"},
        },
    ),
    # -- UACManager --
    _tool(
        "secctl_uac_get_status",
        "Read raw Windows UAC registry values (enabled, consent prompt behavior, secure desktop).",
    ),
    _tool(
        "secctl_uac_get_level",
        "Get UAC as one of the 4 familiar Control Panel slider levels (0=Never notify .. 3=Always notify).",
    ),
    _tool(
        "secctl_uac_set_level",
        "Set UAC to one of the 4 standard slider levels (0-3). Confirm-gated, needs admin + sign-out/restart.",
        {"level": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["level"],
    ),
    _tool(
        "secctl_uac_set_enabled",
        "Turn UAC entirely on or off. Confirm-gated, needs admin + restart.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    # -- AppPermissionsManager --
    _tool(
        "secctl_apppermissions_list_capabilities",
        "List the privacy capability categories this tool can inspect/control (camera, microphone, location, etc.).",
    ),
    _tool(
        "secctl_apppermissions_get_global_status",
        "Get the machine-wide allow/deny toggle for a privacy capability.",
        {"capability": {"type": "string"}},
        ["capability"],
    ),
    _tool(
        "secctl_apppermissions_list_app_access",
        "List every app with a recorded allow/deny grant for a privacy capability.",
        {"capability": {"type": "string"}},
        ["capability"],
    ),
    _tool(
        "secctl_apppermissions_set_global_access",
        "Allow or block ALL apps from a privacy capability machine-wide. Confirm-gated, needs admin.",
        {"capability": {"type": "string"}, "allowed": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["capability", "allowed"],
    ),
    _tool(
        "secctl_apppermissions_set_app_access",
        "Allow or block one specific app's access to a privacy capability. Confirm-gated.",
        {
            "capability": {"type": "string"},
            "app_name": {"type": "string"},
            "allowed": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["capability", "app_name", "allowed"],
    ),
    # -- PrivacyManager --
    _tool(
        "secctl_privacy_get_summary",
        "One-call snapshot of telemetry level, advertising ID, and tailored-experiences status.",
    ),
    _tool(
        "secctl_privacy_get_telemetry_level",
        "Read the current Windows diagnostic-data (telemetry) level.",
    ),
    _tool(
        "secctl_privacy_set_telemetry_level",
        "Set the diagnostic-data level (0=Security, 1=Basic, 2=Enhanced, 3=Full). Confirm-gated, needs admin.",
        {"level": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["level"],
    ),
    _tool(
        "secctl_privacy_get_advertising_id",
        "Read whether the per-user advertising ID is enabled.",
    ),
    _tool(
        "secctl_privacy_set_advertising_id",
        "Enable or disable the per-user advertising ID. Confirm-gated.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_privacy_get_tailored_experiences",
        "Read whether tailored experiences (personalization from diagnostic data) is enabled.",
    ),
    _tool(
        "secctl_privacy_set_tailored_experiences",
        "Enable or disable tailored experiences. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    # -- ActivityHistoryManager --
    _tool(
        "secctl_activityhistory_get_status",
        "Read whether activity collection, local publishing, and cloud upload are enabled.",
    ),
    _tool(
        "secctl_activityhistory_set_collection",
        "Turn Activity History collection on/off machine-wide. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_activityhistory_set_cloud_upload",
        "Turn cross-device cloud sync of activity history on/off. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_activityhistory_clear_local",
        "Clear the local Activity History cache. Irreversible. Confirm-gated.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- CookiesManager (metadata-only; never returns cookie values) --
    _tool(
        "secctl_cookies_list_domains",
        "List domains with stored cookies and counts for a browser (chrome/edge/firefox). Metadata only.",
        {"browser": {"type": "string"}},
    ),
    _tool(
        "secctl_cookies_get_domain_count",
        "Get the stored cookie count for one domain in a browser.",
        {"domain": {"type": "string"}, "browser": {"type": "string"}},
        ["domain"],
    ),
    _tool(
        "secctl_cookies_clear_domain",
        "Delete all cookies for a domain in a browser. Confirm-gated; browser must be closed first.",
        {"domain": {"type": "string"}, "browser": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["domain"],
    ),
    _tool(
        "secctl_cookies_clear_all",
        "Delete ALL cookies for a browser. Confirm-gated; browser must be closed first.",
        {"browser": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    # -- CertificatesManager (public certs only; no private-key export/import) --
    _tool(
        "secctl_certs_list_stores",
        "List the certificate store names/locations this tool can target.",
    ),
    _tool(
        "secctl_certs_list_certificates",
        "List certificates in a store with subject/issuer/thumbprint/expiry.",
        {"store": {"type": "string"}, "location": {"type": "string"}},
    ),
    _tool(
        "secctl_certs_get_certificate",
        "Get full detail for a certificate by thumbprint.",
        {"thumbprint": {"type": "string"}, "store": {"type": "string"}, "location": {"type": "string"}},
        ["thumbprint"],
    ),
    _tool(
        "secctl_certs_list_expiring_soon",
        "List certificates in a store expiring within N days.",
        {"days": {"type": "integer"}, "store": {"type": "string"}, "location": {"type": "string"}},
    ),
    _tool(
        "secctl_certs_export",
        "Export a certificate's PUBLIC key (.cer) by thumbprint. No private-key export exists. Confirm-gated.",
        {
            "thumbprint": {"type": "string"},
            "export_path": {"type": "string"},
            "store": {"type": "string"},
            "location": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["thumbprint", "export_path"],
    ),
    _tool(
        "secctl_certs_import",
        "Import a public certificate file (.cer/.crt/.der; .pfx/.p12 rejected) into a store. Confirm-gated.",
        {
            "cert_path": {"type": "string"},
            "store": {"type": "string"},
            "location": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["cert_path"],
    ),
    _tool(
        "secctl_certs_remove",
        "Delete a certificate from a store by thumbprint. Confirm-gated.",
        {
            "thumbprint": {"type": "string"},
            "store": {"type": "string"},
            "location": {"type": "string"},
            "confirm": {"type": "boolean"},
        },
        ["thumbprint"],
    ),
    # -- SmartScreenManager --
    _tool(
        "secctl_smartscreen_get_status",
        "One-call snapshot of all SmartScreen surfaces: Explorer check-apps-and-files, Store apps web content evaluation, Edge policy.",
    ),
    _tool(
        "secctl_smartscreen_set_explorer",
        "Set the Explorer 'check apps and files' SmartScreen level: Warn, RequireAdmin, or Off. Confirm-gated, needs admin.",
        {"level": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["level"],
    ),
    _tool(
        "secctl_smartscreen_set_store_apps",
        "Enable/disable SmartScreen web content evaluation for Microsoft Store apps. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_smartscreen_set_edge",
        "Set a machine policy forcing Edge SmartScreen on/off, overriding the per-user toggle. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_smartscreen_set_edge_pua",
        "Set a machine policy for Edge's Potentially-Unwanted-Application blocking. Confirm-gated, needs admin.",
        {"enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "secctl_smartscreen_clear_edge_policy",
        "Remove machine-policy overrides for Edge SmartScreen/PUA, returning control to edge://settings. Confirm-gated, needs admin.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- ExploitProtectionManager --
    _tool(
        "secctl_exploitprotect_get_system_settings",
        "Read system-wide default exploit mitigation settings (DEP, ASLR, CFG, SEHOP, etc).",
    ),
    _tool(
        "secctl_exploitprotect_get_app_settings",
        "Read per-app exploit mitigation overrides for one executable.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "secctl_exploitprotect_list_mitigations",
        "List the mitigation names that can be toggled via set_system_mitigation/set_app_mitigation.",
    ),
    _tool(
        "secctl_exploitprotect_set_system_mitigation",
        "Turn one system-wide default mitigation on/off (e.g. CFG, DEP, ASLR, SEHOP). Confirm-gated, needs admin.",
        {"mitigation": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["mitigation", "enabled"],
    ),
    _tool(
        "secctl_exploitprotect_set_app_mitigation",
        "Turn one mitigation on/off for a single named executable, overriding the system default for that app. Confirm-gated, needs admin.",
        {
            "app_name": {"type": "string"},
            "mitigation": {"type": "string"},
            "enabled": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["app_name", "mitigation", "enabled"],
    ),
    _tool(
        "secctl_exploitprotect_remove_app_settings",
        "Remove all per-app mitigation overrides for one executable, reverting it to system defaults. Confirm-gated, needs admin.",
        {"app_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["app_name"],
    ),
    _tool(
        "secctl_exploitprotect_export_settings",
        "Export the full Exploit Protection configuration (system + per-app) to an XML file.",
        {"export_path": {"type": "string"}},
        ["export_path"],
    ),
    _tool(
        "secctl_exploitprotect_import_settings",
        "Import an Exploit Protection XML configuration, replacing current system + per-app settings for anything it covers. Confirm-gated, needs admin.",
        {"import_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["import_path"],
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
SECURITY_CONTROL_DIRECT_HANDLERS = {
    # -- DefenderManager --
    "secctl_defender_get_status": lambda d, _k="defender", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_defender_set_realtime_protection": lambda d, _k="defender", _m="set_realtime_protection", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_defender_set_cloud_protection": lambda d, _k="defender", _m="set_cloud_protection", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_defender_start_scan": lambda d, _k="defender", _m="start_scan", _p=["scan_type", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_defender_update_signatures": lambda d, _k="defender", _m="update_signatures", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_defender_list_threat_history": lambda d, _k="defender", _m="list_threat_history", _p=["limit"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_defender_list_exclusions": lambda d, _k="defender", _m="list_exclusions", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_defender_add_exclusion_path": lambda d, _k="defender", _m="add_exclusion_path", _p=[
        "path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_defender_remove_exclusion_path": lambda d, _k="defender", _m="remove_exclusion_path", _p=[
        "path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- AntivirusManager --
    "secctl_av_list_registered_products": lambda d, _k="antivirus", _m="list_registered_products", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_av_get_active": lambda d, _k="antivirus", _m="get_active_antivirus", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_av_is_outdated": lambda d, _k="antivirus", _m="is_any_av_outdated", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_av_open_security_app": lambda d, _k="antivirus", _m="open_security_app", _p=["page"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- RansomwareProtection --
    "secctl_ransomware_get_status": lambda d, _k="ransomware", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_ransomware_set_enabled": lambda d, _k="ransomware", _m="set_enabled", _p=[
        "enabled",
        "audit_mode",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_ransomware_list_protected_folders": lambda d, _k="ransomware", _m="list_protected_folders", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_ransomware_add_protected_folder": lambda d, _k="ransomware", _m="add_protected_folder", _p=[
        "path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_ransomware_remove_protected_folder": lambda d, _k="ransomware", _m="remove_protected_folder", _p=[
        "path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_ransomware_list_allowed_apps": lambda d, _k="ransomware", _m="list_allowed_apps", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_ransomware_add_allowed_app": lambda d, _k="ransomware", _m="add_allowed_app", _p=[
        "exe_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_ransomware_remove_allowed_app": lambda d, _k="ransomware", _m="remove_allowed_app", _p=[
        "exe_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- BitLockerManager --
    "secctl_bitlocker_list_volumes": lambda d, _k="bitlocker", _m="list_volumes", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_bitlocker_get_status": lambda d, _k="bitlocker", _m="get_status", _p=["drive_letter"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_bitlocker_enable": lambda d, _k="bitlocker", _m="enable_encryption", _p=[
        "drive_letter",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_bitlocker_disable": lambda d, _k="bitlocker", _m="disable_encryption", _p=[
        "drive_letter",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_bitlocker_lock_volume": lambda d, _k="bitlocker", _m="lock_volume", _p=["drive_letter", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_bitlocker_unlock_volume": lambda d, _k="bitlocker", _m="unlock_volume", _p=[
        "drive_letter",
        "password",
        "recovery_key",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_bitlocker_get_recovery_key": lambda d, _k="bitlocker", _m="get_recovery_key", _p=[
        "drive_letter",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- UserAccountsManager --
    "secctl_accounts_list": lambda d, _k="accounts", _m="list_accounts", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_accounts_get_status": lambda d, _k="accounts", _m="get_account_status", _p=["username"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_accounts_create": lambda d, _k="accounts", _m="create_account", _p=[
        "username",
        "password",
        "make_admin",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_accounts_remove": lambda d, _k="accounts", _m="remove_account", _p=["username", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_accounts_set_enabled": lambda d, _k="accounts", _m="set_account_enabled", _p=[
        "username",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_accounts_set_admin": lambda d, _k="accounts", _m="set_admin", _p=[
        "username",
        "is_admin",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_accounts_reset_password": lambda d, _k="accounts", _m="reset_password", _p=[
        "username",
        "new_password",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- PasswordPolicy --
    "secctl_pwpolicy_get": lambda d, _k="password_policy", _m="get_policy", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_pwpolicy_set_min_length": lambda d, _k="password_policy", _m="set_min_password_length", _p=[
        "length",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_pwpolicy_set_max_age": lambda d, _k="password_policy", _m="set_max_password_age", _p=[
        "days",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_pwpolicy_set_min_age": lambda d, _k="password_policy", _m="set_min_password_age", _p=[
        "days",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_pwpolicy_set_history": lambda d, _k="password_policy", _m="set_password_history", _p=[
        "count",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_pwpolicy_set_lockout": lambda d, _k="password_policy", _m="set_lockout_policy", _p=[
        "threshold",
        "duration_minutes",
        "observation_window_minutes",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- UACManager --
    "secctl_uac_get_status": lambda d, _k="uac", _m="get_status", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_uac_get_level": lambda d, _k="uac", _m="get_level", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_uac_set_level": lambda d, _k="uac", _m="set_level", _p=["level", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_uac_set_enabled": lambda d, _k="uac", _m="set_enabled", _p=["enabled", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- AppPermissionsManager --
    "secctl_apppermissions_list_capabilities": lambda d, _k="app_permissions", _m="list_capabilities", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_apppermissions_get_global_status": lambda d, _k="app_permissions", _m="get_global_status", _p=[
        "capability"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_apppermissions_list_app_access": lambda d, _k="app_permissions", _m="list_app_access", _p=[
        "capability"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_apppermissions_set_global_access": lambda d, _k="app_permissions", _m="set_global_access", _p=[
        "capability",
        "allowed",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_apppermissions_set_app_access": lambda d, _k="app_permissions", _m="set_app_access", _p=[
        "capability",
        "app_name",
        "allowed",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- PrivacyManager --
    "secctl_privacy_get_summary": lambda d, _k="privacy", _m="get_summary", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_privacy_get_telemetry_level": lambda d, _k="privacy", _m="get_telemetry_level", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_privacy_set_telemetry_level": lambda d, _k="privacy", _m="set_telemetry_level", _p=[
        "level",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_privacy_get_advertising_id": lambda d, _k="privacy", _m="get_advertising_id_status", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "secctl_privacy_set_advertising_id": lambda d, _k="privacy", _m="set_advertising_id", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_privacy_get_tailored_experiences": lambda d, _k="privacy", _m="get_tailored_experiences_status", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "secctl_privacy_set_tailored_experiences": lambda d, _k="privacy", _m="set_tailored_experiences", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- ActivityHistoryManager --
    "secctl_activityhistory_get_status": lambda d, _k="activity_history", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_activityhistory_set_collection": lambda d, _k="activity_history", _m="set_collection_enabled", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_activityhistory_set_cloud_upload": lambda d, _k="activity_history", _m="set_cloud_upload_enabled", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_activityhistory_clear_local": lambda d, _k="activity_history", _m="clear_local_history", _p=[
        "confirm"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- CookiesManager --
    "secctl_cookies_list_domains": lambda d, _k="cookies", _m="list_domains", _p=["browser"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_cookies_get_domain_count": lambda d, _k="cookies", _m="get_domain_cookie_count", _p=[
        "domain",
        "browser",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_cookies_clear_domain": lambda d, _k="cookies", _m="clear_domain", _p=[
        "domain",
        "browser",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_cookies_clear_all": lambda d, _k="cookies", _m="clear_all", _p=["browser", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- CertificatesManager --
    "secctl_certs_list_stores": lambda d, _k="certificates", _m="list_stores", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_certs_list_certificates": lambda d, _k="certificates", _m="list_certificates", _p=[
        "store",
        "location",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_certs_get_certificate": lambda d, _k="certificates", _m="get_certificate", _p=[
        "thumbprint",
        "store",
        "location",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_certs_list_expiring_soon": lambda d, _k="certificates", _m="list_expiring_soon", _p=[
        "days",
        "store",
        "location",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_certs_export": lambda d, _k="certificates", _m="export_certificate", _p=[
        "thumbprint",
        "export_path",
        "store",
        "location",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_certs_import": lambda d, _k="certificates", _m="import_certificate", _p=[
        "cert_path",
        "store",
        "location",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_certs_remove": lambda d, _k="certificates", _m="remove_certificate", _p=[
        "thumbprint",
        "store",
        "location",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- SmartScreenManager --
    "secctl_smartscreen_get_status": lambda d, _k="smartscreen", _m="get_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "secctl_smartscreen_set_explorer": lambda d, _k="smartscreen", _m="set_explorer_smartscreen", _p=[
        "level",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_smartscreen_set_store_apps": lambda d, _k="smartscreen", _m="set_store_apps_smartscreen", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_smartscreen_set_edge": lambda d, _k="smartscreen", _m="set_edge_smartscreen", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_smartscreen_set_edge_pua": lambda d, _k="smartscreen", _m="set_edge_pua_blocking", _p=[
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_smartscreen_clear_edge_policy": lambda d, _k="smartscreen", _m="clear_edge_policy", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- ExploitProtectionManager --
    "secctl_exploitprotect_get_system_settings": lambda d, _k="exploit_protection", _m="get_system_settings", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "secctl_exploitprotect_get_app_settings": lambda d, _k="exploit_protection", _m="get_app_settings", _p=[
        "app_name"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_exploitprotect_list_mitigations": lambda d, _k="exploit_protection", _m="list_known_mitigations", _p=[]: getattr(
        _get(_k), _m
    )(
        **_pick(d, _p)
    ),
    "secctl_exploitprotect_set_system_mitigation": lambda d, _k="exploit_protection", _m="set_system_mitigation", _p=[
        "mitigation",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_exploitprotect_set_app_mitigation": lambda d, _k="exploit_protection", _m="set_app_mitigation", _p=[
        "app_name",
        "mitigation",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_exploitprotect_remove_app_settings": lambda d, _k="exploit_protection", _m="remove_app_settings", _p=[
        "app_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_exploitprotect_export_settings": lambda d, _k="exploit_protection", _m="export_settings", _p=[
        "export_path"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "secctl_exploitprotect_import_settings": lambda d, _k="exploit_protection", _m="import_settings", _p=[
        "import_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
}
