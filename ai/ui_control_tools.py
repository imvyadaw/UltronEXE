"""UI Control tool registry
============================
Wires system_control/ui/* (theme/dark-mode, accent color, taskbar,
Start menu, mouse cursor, lock screen, notification settings, Widgets
board) into the AI tool-calling loop. Same pattern as
ai/security_control_tools.py and ai/network_control_tools.py: lazy
singletons + a flat UI_CONTROL_TOOLS / UI_CONTROL_DIRECT_HANDLERS
pair, merged at the bottom of ai/tools_schema.py and
ai/tool_runtime.py respectively (see the two-line imports there).

Naming: every tool is prefixed `uictl_` to avoid colliding with the
existing `ui_*` tools elsewhere (those drive ULTRON's OWN orb/overlay/
dashboard interface, not the Windows shell - see
system_control/ui/__init__.py's docstring for the same distinction
spelled out at the package level).

Most methods here are per-user cosmetic preferences and are NOT
confirm-gated (same class as any other UI-preference toggle) - this
mirrors the underlying classes' own confirm-gating choices rather than
gating everything uniformly. The few exceptions that ARE confirm-gated
(explorer restart, Start layout import) are genuinely disruptive or
replace existing user content, and the underlying classes gate them
for that reason.
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

    if key == "theme":
        from system_control.ui.theme_manager import ThemeManager

        obj = ThemeManager()
    elif key == "accent":
        from system_control.ui.accent_color import AccentColorManager

        obj = AccentColorManager()
    elif key == "taskbar":
        from system_control.ui.taskbar_manager import TaskbarManager

        obj = TaskbarManager()
    elif key == "start_menu":
        from system_control.ui.start_menu_manager import StartMenuManager

        obj = StartMenuManager()
    elif key == "desktop_icons":
        from system_control.ui.desktop_icons import DesktopIconManager

        obj = DesktopIconManager()
    elif key == "font":
        from system_control.ui.font_manager import FontManager

        obj = FontManager()
    elif key == "display_res":
        from system_control.ui.display_resolution import DisplayResolutionManager

        obj = DisplayResolutionManager()
    elif key == "display_scaling":
        from system_control.ui.display_scaling import DisplayScalingManager

        obj = DisplayScalingManager()
    elif key == "multi_display":
        from system_control.ui.multi_display import MultiDisplayManager

        obj = MultiDisplayManager()
    elif key == "sound":
        from system_control.ui.sound_manager import SoundManager

        obj = SoundManager()
    elif key == "cursor":
        from system_control.ui.cursor_manager import CursorManager

        obj = CursorManager()
    elif key == "lock_screen":
        from system_control.ui.lock_screen import LockScreenManager

        obj = LockScreenManager()
    elif key == "notification":
        from system_control.ui.notification_manager import NotificationManager

        obj = NotificationManager()
    elif key == "widgets":
        from system_control.ui.widgets_manager import WidgetsManager

        obj = WidgetsManager()
    else:
        raise KeyError(f"Unknown ui_control tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
UI_CONTROL_TOOLS = [
    # -- ThemeManager --
    _tool(
        "uictl_theme_get_status",
        "Read whether apps/system UI use light or dark mode, and whether transparency effects are on.",
    ),
    _tool(
        "uictl_theme_set_app_mode",
        "Set whether apps (Settings, Explorer, most Store apps) render dark or light.",
        {"dark": {"type": "boolean"}},
        ["dark"],
    ),
    _tool(
        "uictl_theme_set_system_mode",
        "Set whether system UI (taskbar, Start, action center) renders dark or light.",
        {"dark": {"type": "boolean"}},
        ["dark"],
    ),
    _tool(
        "uictl_theme_set_mode",
        "Set both apps and system UI to the same dark/light mode in one call.",
        {"dark": {"type": "boolean"}},
        ["dark"],
    ),
    _tool(
        "uictl_theme_set_transparency",
        "Turn transparency/blur effects (Start, taskbar, action center) on or off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_theme_list_installed",
        "List available .theme files (built-in Windows themes plus saved/synced ones).",
    ),
    _tool(
        "uictl_theme_apply",
        "Apply a .theme file by path, same as double-clicking it in Explorer.",
        {"theme_path": {"type": "string"}},
        ["theme_path"],
    ),
    # -- AccentColorManager --
    _tool(
        "uictl_accent_get_color",
        "Read the current Windows accent color as a '#RRGGBB' hex string.",
    ),
    _tool(
        "uictl_accent_set_color",
        "Set a specific accent color from a '#RRGGBB' hex string. Turns off auto-from-background.",
        {"hex_color": {"type": "string"}},
        ["hex_color"],
    ),
    _tool(
        "uictl_accent_get_auto_from_background",
        "Read whether Windows picks the accent color automatically from the wallpaper.",
    ),
    _tool(
        "uictl_accent_set_auto_from_background",
        "Turn 'automatically pick an accent color from my background' on or off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_accent_get_color_prevalence",
        "Read whether the accent color is shown on Start, taskbar, and action center.",
    ),
    _tool(
        "uictl_accent_set_color_prevalence",
        "Turn 'show accent color on Start, taskbar, and action center' on or off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_accent_get_title_bar_prevalence",
        "Read whether the accent color is shown on window title bars and borders.",
    ),
    _tool(
        "uictl_accent_set_title_bar_prevalence",
        "Turn 'show accent color on title bars and window borders' on or off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    # -- TaskbarManager --
    _tool(
        "uictl_taskbar_get_settings",
        "Read taskbar alignment, small-icons, widgets, task view button, and search box mode.",
    ),
    _tool(
        "uictl_taskbar_set_alignment",
        "Set taskbar icon alignment: 'left' or 'center' (Windows 11).",
        {"position": {"type": "string"}},
        ["position"],
    ),
    _tool(
        "uictl_taskbar_set_small_icons",
        "Turn small taskbar icons on/off. Call uictl_taskbar_restart_explorer to apply immediately.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_taskbar_set_search_box_mode",
        "Set taskbar search box display: 'hidden', 'icon', 'icon_and_label', or 'box'.",
        {"mode": {"type": "string"}},
        ["mode"],
    ),
    _tool(
        "uictl_taskbar_set_widgets_visible",
        "Show/hide the Widgets icon on the taskbar.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_taskbar_set_task_view_visible",
        "Show/hide the Task View button on the taskbar.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_taskbar_get_autohide",
        "Read whether the taskbar is currently set to auto-hide.",
    ),
    _tool(
        "uictl_taskbar_set_autohide",
        "Turn taskbar auto-hide on/off immediately (no Explorer restart needed).",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_taskbar_restart_explorer",
        "Restart explorer.exe to apply pending taskbar registry settings. Confirm-gated - briefly closes the desktop shell.",
        {"confirm": {"type": "boolean"}},
    ),
    # -- StartMenuManager --
    _tool(
        "uictl_startmenu_get_settings",
        "Read Start menu content settings: recent items, frequently used apps, recommended files.",
    ),
    _tool(
        "uictl_startmenu_set_show_recent_items",
        "Turn 'show recently opened items in Jump Lists, Start, and File Explorer' on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_startmenu_set_show_frequent_apps",
        "Turn 'show most used apps' on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_startmenu_set_show_recommended",
        "Turn Windows 11's 'Recommended' (recently used/suggested files) section on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_startmenu_export_layout",
        "Export the current Start layout to an XML file.",
        {"export_path": {"type": "string"}},
        ["export_path"],
    ),
    _tool(
        "uictl_startmenu_import_layout",
        "Apply a Start layout XML, replacing current pinned content. Confirm-gated, needs admin.",
        {"layout_path": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["layout_path"],
    ),
    _tool(
        "uictl_startmenu_pin_app",
        "Best-effort pin an app/shortcut to Start (unofficial verb - may not exist on all Windows builds).",
        {"app_path": {"type": "string"}},
        ["app_path"],
    ),
    _tool(
        "uictl_startmenu_unpin_app",
        "Best-effort unpin an app from Start (unofficial verb - may not exist on all Windows builds).",
        {"app_path": {"type": "string"}},
        ["app_path"],
    ),
    _tool(
        "uictl_startmenu_open",
        "Open the Start menu (simulates pressing the Windows key).",
    ),
    # -- DesktopIconManager --
    _tool(
        "uictl_desktopicons_get_show_all",
        "Read whether desktop icons are shown at all.",
    ),
    _tool(
        "uictl_desktopicons_set_show_all",
        "Turn ALL desktop icons on/off in one go.",
        {"visible": {"type": "boolean"}},
        ["visible"],
    ),
    _tool(
        "uictl_desktopicons_list_names",
        "List the special desktop icon names that can be toggled individually (this_pc, recycle_bin, user_files, network, control_panel).",
    ),
    _tool(
        "uictl_desktopicons_get_visibility",
        "Read whether one special desktop icon (this_pc/recycle_bin/user_files/network/control_panel) is shown.",
        {"icon": {"type": "string"}},
        ["icon"],
    ),
    _tool(
        "uictl_desktopicons_set_visibility",
        "Show/hide one special desktop icon (this_pc/recycle_bin/user_files/network/control_panel).",
        {"icon": {"type": "string"}, "visible": {"type": "boolean"}},
        ["icon", "visible"],
    ),
    _tool(
        "uictl_desktopicons_get_size",
        "Read the current desktop icon size in pixels and its closest small/medium/large label.",
    ),
    _tool(
        "uictl_desktopicons_set_size",
        "Set desktop icon size: 'small', 'medium', or 'large'.",
        {"size": {"type": "string"}},
        ["size"],
    ),
    _tool(
        "uictl_desktopicons_get_layout",
        "Read whether desktop icons are set to auto-arrange and/or align to grid.",
    ),
    _tool(
        "uictl_desktopicons_set_layout",
        "Turn 'Auto arrange icons' and/or 'Align icons to grid' on/off. Omit a flag to leave it unchanged.",
        {"auto_arrange": {"type": "boolean"}, "align_to_grid": {"type": "boolean"}},
    ),
    # -- FontManager --
    _tool(
        "uictl_font_list_installed",
        "List installed fonts: system-wide and per-user.",
    ),
    _tool(
        "uictl_font_install",
        "Install a .ttf/.ttc/.otf/.fon file for the current user (no admin needed).",
        {"font_path": {"type": "string"}},
        ["font_path"],
    ),
    _tool(
        "uictl_font_uninstall",
        "Remove a per-user-installed font by name. Confirm-gated - deletes a file.",
        {"font_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["font_name"],
    ),
    _tool(
        "uictl_font_get_smoothing",
        "Read whether font smoothing is on and whether it's standard or ClearType.",
    ),
    _tool(
        "uictl_font_set_cleartype",
        "Turn ClearType text rendering on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_font_get_ui_font_substitute",
        "Read what the default system UI font ('Segoe UI') is currently substituted with, if anything.",
    ),
    _tool(
        "uictl_font_set_ui_font_substitute",
        "Replace the system UI font by substituting 'Segoe UI' with another font (pass no font_name to clear it). Confirm-gated - needs admin, needs sign-out, can hurt readability.",
        {"font_name": {"type": "string"}, "confirm": {"type": "boolean"}},
    ),
    # -- DisplayResolutionManager --
    _tool(
        "uictl_display_list_devices",
        "Enumerate Windows display device names (e.g. '\\\\.\\DISPLAY1') for every attached monitor.",
    ),
    _tool(
        "uictl_display_get_resolution",
        "Get a monitor's current resolution and refresh rate. Omit device_name for the primary display.",
        {"device_name": {"type": "string"}},
    ),
    _tool(
        "uictl_display_list_supported_modes",
        "List every resolution/refresh-rate combination a monitor supports. Omit device_name for the primary display.",
        {"device_name": {"type": "string"}},
    ),
    _tool(
        "uictl_display_set_resolution",
        "Set a monitor's resolution (and optionally refresh rate). Omit device_name for the primary display.",
        {
            "width": {"type": "integer"},
            "height": {"type": "integer"},
            "device_name": {"type": "string"},
            "refresh_rate_hz": {"type": "integer"},
        },
        ["width", "height"],
    ),
    _tool(
        "uictl_display_set_refresh_rate",
        "Set a monitor's refresh rate, keeping its current resolution. Omit device_name for the primary display.",
        {"refresh_rate_hz": {"type": "integer"}, "device_name": {"type": "string"}},
        ["refresh_rate_hz"],
    ),
    # -- DisplayScalingManager --
    _tool(
        "uictl_scaling_get",
        "Read the current system DPI scaling percentage (100/125/150/etc).",
    ),
    _tool(
        "uictl_scaling_set",
        "Request a new DPI scaling percentage (100/125/150/175/200/etc). Confirm-gated - needs sign-out to fully apply.",
        {"percent": {"type": "integer"}, "device_id": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["percent"],
    ),
    _tool(
        "uictl_textscale_get",
        "Read the Windows 11 accessibility 'Text size' slider value (100-225).",
    ),
    _tool(
        "uictl_textscale_set",
        "Set the accessibility 'Text size' slider (100-225). Applies live, no sign-out needed - use this for a plain 'make text bigger' request.",
        {"percent": {"type": "integer"}},
        ["percent"],
    ),
    # -- MultiDisplayManager --
    _tool(
        "uictl_multidisplay_list",
        "List every attached display with device name, resolution, refresh rate, and virtual-screen position.",
    ),
    _tool(
        "uictl_multidisplay_get_mode",
        "Read the current display mode (extend/duplicate/pc_screen_only, best-effort).",
    ),
    _tool(
        "uictl_multidisplay_set_mode",
        "Switch display mode: 'extend', 'duplicate', 'second_screen_only', or 'pc_screen_only' (same as Win+P). Confirm-gated - can blank screens momentarily.",
        {"mode": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["mode"],
    ),
    _tool(
        "uictl_multidisplay_set_primary",
        "Make the given device the primary display. Confirm-gated - moves the taskbar and re-anchors maximized windows.",
        {"device_name": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["device_name"],
    ),
    _tool(
        "uictl_multidisplay_set_position",
        "Move a monitor's position in the virtual-desktop arrangement grid.",
        {"device_name": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}},
        ["device_name", "x", "y"],
    ),
    # -- SoundManager --
    _tool(
        "uictl_sound_list_playback_devices",
        "List playback (output) devices.",
    ),
    _tool(
        "uictl_sound_list_recording_devices",
        "List recording (input/microphone) devices.",
    ),
    _tool(
        "uictl_sound_get_default_playback",
        "Read the current default output device.",
    ),
    _tool(
        "uictl_sound_set_default_playback",
        "Switch the default output device by name or list index. Confirm-gated - audio suddenly moves to a different device.",
        {"name_or_index": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name_or_index"],
    ),
    _tool(
        "uictl_sound_get_default_recording",
        "Read the current default input (microphone) device.",
    ),
    _tool(
        "uictl_sound_set_default_recording",
        "Switch the default input device by name or list index. Confirm-gated - a listening app could suddenly hear nothing.",
        {"name_or_index": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["name_or_index"],
    ),
    _tool(
        "uictl_sound_list_app_sessions",
        "List running apps that currently have an audio session (Volume Mixer entries) with their volume/mute state.",
    ),
    _tool(
        "uictl_sound_get_app_volume",
        "Read a specific app's Volume Mixer level by process name.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "uictl_sound_set_app_volume",
        "Set a specific app's Volume Mixer level (0-100) by process name.",
        {"app_name": {"type": "string"}, "level": {"type": "integer"}},
        ["app_name", "level"],
    ),
    _tool(
        "uictl_sound_set_app_mute",
        "Mute/unmute a specific app in the Volume Mixer by process name.",
        {"app_name": {"type": "string"}, "muted": {"type": "boolean"}},
        ["app_name", "muted"],
    ),
    _tool(
        "uictl_sound_get_scheme",
        "Read the currently active sound scheme name.",
    ),
    _tool(
        "uictl_sound_list_schemes",
        "List available sound scheme names.",
    ),
    _tool(
        "uictl_sound_apply_scheme",
        "Switch the active sound scheme (which .wav plays for system events).",
        {"scheme_name": {"type": "string"}},
        ["scheme_name"],
    ),
    # -- CursorManager --
    _tool(
        "uictl_cursor_get_scheme",
        "Read the active mouse cursor scheme name.",
    ),
    _tool(
        "uictl_cursor_list_schemes",
        "List available cursor scheme names (built-in and saved).",
    ),
    _tool(
        "uictl_cursor_set_scheme",
        "Switch to a named cursor scheme, applied immediately.",
        {"scheme_name": {"type": "string"}},
        ["scheme_name"],
    ),
    _tool(
        "uictl_cursor_set_cursor",
        "Set a single cursor role (Arrow/Hand/IBeam/etc.) to a specific .cur/.ani file.",
        {"role": {"type": "string"}, "cursor_path": {"type": "string"}},
        ["role", "cursor_path"],
    ),
    _tool(
        "uictl_cursor_get_pointer_speed",
        "Read pointer speed (1-20) and whether 'Enhance pointer precision' is on.",
    ),
    _tool(
        "uictl_cursor_set_pointer_speed",
        "Set pointer speed, 1 (slowest) to 20 (fastest).",
        {"speed": {"type": "integer"}},
        ["speed"],
    ),
    _tool(
        "uictl_cursor_set_enhance_precision",
        "Turn 'Enhance pointer precision' (pointer acceleration) on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_cursor_get_trails",
        "Read whether pointer trails are on and their length.",
    ),
    _tool(
        "uictl_cursor_set_trails",
        "Turn pointer trails on/off, with optional trail length (2-10).",
        {"enabled": {"type": "boolean"}, "length": {"type": "integer"}},
        ["enabled"],
    ),
    _tool(
        "uictl_cursor_get_snap_to_default_button",
        "Read whether the pointer auto-snaps to a dialog's default button.",
    ),
    _tool(
        "uictl_cursor_set_snap_to_default_button",
        "Turn 'automatically move pointer to the default button in a dialog' on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_cursor_get_pointer_size",
        "Read the accessibility pointer size in pixels.",
    ),
    _tool(
        "uictl_cursor_set_pointer_size",
        "Set the accessibility pointer size in pixels (32=default, up to ~256).",
        {"size_px": {"type": "integer"}},
        ["size_px"],
    ),
    _tool(
        "uictl_cursor_get_pointer_color",
        "Read the accessibility pointer color as '#RRGGBB', or null if default.",
    ),
    _tool(
        "uictl_cursor_set_pointer_color",
        "Set a custom accessibility pointer color from '#RRGGBB'.",
        {"hex_color": {"type": "string"}},
        ["hex_color"],
    ),
    # -- LockScreenManager --
    _tool(
        "uictl_lockscreen_get_background_mode",
        "Read the lock screen background mode: windows_spotlight, picture, or unknown.",
    ),
    _tool(
        "uictl_lockscreen_set_spotlight",
        "Switch the lock screen to Windows Spotlight, with optional fun-facts overlay.",
        {"show_fun_facts": {"type": "boolean"}},
    ),
    _tool(
        "uictl_lockscreen_set_picture",
        "Set a static picture as the lock screen background.",
        {"image_path": {"type": "string"}},
        ["image_path"],
    ),
    _tool(
        "uictl_lockscreen_get_timeout",
        "Read the idle time before the lock screen engages, and whether sign-in is required on resume.",
    ),
    _tool(
        "uictl_lockscreen_set_timeout",
        "Set the idle time (seconds, 0=off) before Windows locks the session.",
        {"timeout_seconds": {"type": "integer"}, "require_signin_on_resume": {"type": "boolean"}},
        ["timeout_seconds"],
    ),
    _tool(
        "uictl_lockscreen_get_detailed_status",
        "Read whether the Spotlight 'fun facts, tips, and more' overlay text is shown.",
    ),
    _tool(
        "uictl_lockscreen_set_detailed_status",
        "Turn the Spotlight 'fun facts, tips, and more' overlay text on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    # -- NotificationManager --
    _tool(
        "uictl_notif_get_enabled",
        "Read the master notifications toggle and lock-screen visibility.",
    ),
    _tool(
        "uictl_notif_set_enabled",
        "Turn ALL notifications on/off (the master switch).",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_notif_set_show_on_lock_screen",
        "Turn 'notifications on the lock screen' on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_notif_list_app_ids",
        "List app ids (AUMIDs) that have a per-app notification entry.",
    ),
    _tool(
        "uictl_notif_get_app_settings",
        "Read one app's notification settings (enabled, sound, action center).",
        {"app_id": {"type": "string"}},
        ["app_id"],
    ),
    _tool(
        "uictl_notif_set_app_enabled",
        "Turn one app's notifications on/off entirely, by app id.",
        {"app_id": {"type": "string"}, "enabled": {"type": "boolean"}},
        ["app_id", "enabled"],
    ),
    _tool(
        "uictl_notif_set_app_sound_enabled",
        "Turn one app's notification sound on/off, by app id.",
        {"app_id": {"type": "string"}, "enabled": {"type": "boolean"}},
        ["app_id", "enabled"],
    ),
    _tool(
        "uictl_notif_set_app_show_in_action_center",
        "Turn whether one app's notifications persist in Action Center on/off, by app id.",
        {"app_id": {"type": "string"}, "enabled": {"type": "boolean"}},
        ["app_id", "enabled"],
    ),
    _tool(
        "uictl_notif_get_focus_assist_mode",
        "Best-effort read of Focus Assist's current mode (off/priority_only/alarms_only/unknown).",
    ),
    _tool(
        "uictl_notif_set_focus_assist_mode",
        "Best-effort set Focus Assist mode: off, priority_only, or alarms_only. Confirm-gated.",
        {"mode": {"type": "string"}, "confirm": {"type": "boolean"}},
        ["mode"],
    ),
    # -- WidgetsManager --
    _tool(
        "uictl_widgets_open",
        "Open the Windows 11 Widgets board.",
    ),
    _tool(
        "uictl_widgets_close",
        "Close the Widgets board if it's open.",
    ),
    _tool(
        "uictl_widgets_get_open_on_hover",
        "Read whether hovering the taskbar Widgets icon opens the board automatically.",
    ),
    _tool(
        "uictl_widgets_set_open_on_hover",
        "Turn 'open Widgets by hovering the taskbar icon' on/off.",
        {"enabled": {"type": "boolean"}},
        ["enabled"],
    ),
    _tool(
        "uictl_widgets_get_allowed",
        "Read whether the Widgets feature is allowed machine-wide by policy.",
    ),
    _tool(
        "uictl_widgets_set_allowed",
        "Allow or fully disable the Widgets feature machine-wide via policy. Confirm-gated, needs admin.",
        {"allowed": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["allowed"],
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers - flat name -> lambda(args_dict) -> result dict
# ---------------------------------------------------------------------------
UI_CONTROL_DIRECT_HANDLERS = {
    # -- ThemeManager --
    "uictl_theme_get_status": lambda d, _k="theme", _m="get_status", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_theme_set_app_mode": lambda d, _k="theme", _m="set_app_mode", _p=["dark"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_theme_set_system_mode": lambda d, _k="theme", _m="set_system_mode", _p=["dark"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_theme_set_mode": lambda d, _k="theme", _m="set_mode", _p=["dark"]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_theme_set_transparency": lambda d, _k="theme", _m="set_transparency", _p=["enabled"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_theme_list_installed": lambda d, _k="theme", _m="list_installed_themes", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_theme_apply": lambda d, _k="theme", _m="apply_theme", _p=["theme_path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- AccentColorManager --
    "uictl_accent_get_color": lambda d, _k="accent", _m="get_accent_color", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_accent_set_color": lambda d, _k="accent", _m="set_accent_color", _p=["hex_color"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_accent_get_auto_from_background": lambda d, _k="accent", _m="get_auto_from_background", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_accent_set_auto_from_background": lambda d, _k="accent", _m="set_auto_from_background", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_accent_get_color_prevalence": lambda d, _k="accent", _m="get_color_prevalence", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_accent_set_color_prevalence": lambda d, _k="accent", _m="set_color_prevalence", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_accent_get_title_bar_prevalence": lambda d, _k="accent", _m="get_title_bar_prevalence", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_accent_set_title_bar_prevalence": lambda d, _k="accent", _m="set_title_bar_prevalence", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- TaskbarManager --
    "uictl_taskbar_get_settings": lambda d, _k="taskbar", _m="get_settings", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_taskbar_set_alignment": lambda d, _k="taskbar", _m="set_alignment", _p=["position"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_taskbar_set_small_icons": lambda d, _k="taskbar", _m="set_small_icons", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_taskbar_set_search_box_mode": lambda d, _k="taskbar", _m="set_search_box_mode", _p=["mode"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_taskbar_set_widgets_visible": lambda d, _k="taskbar", _m="set_widgets_visible", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_taskbar_set_task_view_visible": lambda d, _k="taskbar", _m="set_task_view_visible", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_taskbar_get_autohide": lambda d, _k="taskbar", _m="get_autohide", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_taskbar_set_autohide": lambda d, _k="taskbar", _m="set_autohide", _p=["enabled"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_taskbar_restart_explorer": lambda d, _k="taskbar", _m="restart_explorer", _p=["confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- StartMenuManager --
    "uictl_startmenu_get_settings": lambda d, _k="start_menu", _m="get_settings", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_startmenu_set_show_recent_items": lambda d, _k="start_menu", _m="set_show_recent_items", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_startmenu_set_show_frequent_apps": lambda d, _k="start_menu", _m="set_show_frequently_used_apps", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_startmenu_set_show_recommended": lambda d, _k="start_menu", _m="set_show_recommended_files", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_startmenu_export_layout": lambda d, _k="start_menu", _m="export_layout", _p=["export_path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_startmenu_import_layout": lambda d, _k="start_menu", _m="import_layout", _p=[
        "layout_path",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_startmenu_pin_app": lambda d, _k="start_menu", _m="pin_app", _p=["app_path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_startmenu_unpin_app": lambda d, _k="start_menu", _m="unpin_app", _p=["app_path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_startmenu_open": lambda d, _k="start_menu", _m="open_start_menu", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- DesktopIconManager --
    "uictl_desktopicons_get_show_all": lambda d, _k="desktop_icons", _m="get_show_desktop_icons", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_desktopicons_set_show_all": lambda d, _k="desktop_icons", _m="set_show_desktop_icons", _p=[
        "visible"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_desktopicons_list_names": lambda d, _k="desktop_icons", _m="list_icon_names", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_desktopicons_get_visibility": lambda d, _k="desktop_icons", _m="get_icon_visibility", _p=["icon"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_desktopicons_set_visibility": lambda d, _k="desktop_icons", _m="set_icon_visibility", _p=[
        "icon",
        "visible",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_desktopicons_get_size": lambda d, _k="desktop_icons", _m="get_icon_size", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_desktopicons_set_size": lambda d, _k="desktop_icons", _m="set_icon_size", _p=["size"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_desktopicons_get_layout": lambda d, _k="desktop_icons", _m="get_layout", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_desktopicons_set_layout": lambda d, _k="desktop_icons", _m="set_layout", _p=[
        "auto_arrange",
        "align_to_grid",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- FontManager --
    "uictl_font_list_installed": lambda d, _k="font", _m="list_installed_fonts", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_font_install": lambda d, _k="font", _m="install_font", _p=["font_path"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_font_uninstall": lambda d, _k="font", _m="uninstall_font", _p=["font_name", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_font_get_smoothing": lambda d, _k="font", _m="get_font_smoothing", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_font_set_cleartype": lambda d, _k="font", _m="set_cleartype", _p=["enabled"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_font_get_ui_font_substitute": lambda d, _k="font", _m="get_default_ui_font_substitute", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_font_set_ui_font_substitute": lambda d, _k="font", _m="set_default_ui_font_substitute", _p=[
        "font_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- DisplayResolutionManager --
    "uictl_display_list_devices": lambda d, _k="display_res", _m="list_devices", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_display_get_resolution": lambda d, _k="display_res", _m="get_resolution", _p=["device_name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_display_list_supported_modes": lambda d, _k="display_res", _m="list_supported_modes", _p=[
        "device_name"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_display_set_resolution": lambda d, _k="display_res", _m="set_resolution", _p=[
        "width",
        "height",
        "device_name",
        "refresh_rate_hz",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_display_set_refresh_rate": lambda d, _k="display_res", _m="set_refresh_rate", _p=[
        "refresh_rate_hz",
        "device_name",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- DisplayScalingManager --
    "uictl_scaling_get": lambda d, _k="display_scaling", _m="get_scaling", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_scaling_set": lambda d, _k="display_scaling", _m="set_scaling", _p=[
        "percent",
        "device_id",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_textscale_get": lambda d, _k="display_scaling", _m="get_text_scale", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_textscale_set": lambda d, _k="display_scaling", _m="set_text_scale", _p=["percent"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- MultiDisplayManager --
    "uictl_multidisplay_list": lambda d, _k="multi_display", _m="list_displays", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_multidisplay_get_mode": lambda d, _k="multi_display", _m="get_display_mode", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_multidisplay_set_mode": lambda d, _k="multi_display", _m="set_display_mode", _p=["mode", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_multidisplay_set_primary": lambda d, _k="multi_display", _m="set_primary_display", _p=[
        "device_name",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_multidisplay_set_position": lambda d, _k="multi_display", _m="set_display_position", _p=[
        "device_name",
        "x",
        "y",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- SoundManager --
    "uictl_sound_list_playback_devices": lambda d, _k="sound", _m="list_playback_devices", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_sound_list_recording_devices": lambda d, _k="sound", _m="list_recording_devices", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_sound_get_default_playback": lambda d, _k="sound", _m="get_default_playback_device", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_sound_set_default_playback": lambda d, _k="sound", _m="set_default_playback_device", _p=[
        "name_or_index",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_sound_get_default_recording": lambda d, _k="sound", _m="get_default_recording_device", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_sound_set_default_recording": lambda d, _k="sound", _m="set_default_recording_device", _p=[
        "name_or_index",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_sound_list_app_sessions": lambda d, _k="sound", _m="list_app_sessions", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_sound_get_app_volume": lambda d, _k="sound", _m="get_app_volume", _p=["app_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_sound_set_app_volume": lambda d, _k="sound", _m="set_app_volume", _p=["app_name", "level"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_sound_set_app_mute": lambda d, _k="sound", _m="set_app_mute", _p=["app_name", "muted"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_sound_get_scheme": lambda d, _k="sound", _m="get_sound_scheme", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_sound_list_schemes": lambda d, _k="sound", _m="list_sound_schemes", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_sound_apply_scheme": lambda d, _k="sound", _m="apply_sound_scheme", _p=["scheme_name"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- CursorManager --
    "uictl_cursor_get_scheme": lambda d, _k="cursor", _m="get_scheme", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_cursor_list_schemes": lambda d, _k="cursor", _m="list_schemes", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_cursor_set_scheme": lambda d, _k="cursor", _m="set_scheme", _p=["scheme_name"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_cursor_set_cursor": lambda d, _k="cursor", _m="set_cursor", _p=["role", "cursor_path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_cursor_get_pointer_speed": lambda d, _k="cursor", _m="get_pointer_speed", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_cursor_set_pointer_speed": lambda d, _k="cursor", _m="set_pointer_speed", _p=["speed"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_cursor_set_enhance_precision": lambda d, _k="cursor", _m="set_enhance_pointer_precision", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_cursor_get_trails": lambda d, _k="cursor", _m="get_pointer_trails", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_cursor_set_trails": lambda d, _k="cursor", _m="set_pointer_trails", _p=["enabled", "length"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_cursor_get_snap_to_default_button": lambda d, _k="cursor", _m="get_snap_to_default_button", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_cursor_set_snap_to_default_button": lambda d, _k="cursor", _m="set_snap_to_default_button", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_cursor_get_pointer_size": lambda d, _k="cursor", _m="get_pointer_size", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_cursor_set_pointer_size": lambda d, _k="cursor", _m="set_pointer_size", _p=["size_px"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_cursor_get_pointer_color": lambda d, _k="cursor", _m="get_pointer_color", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_cursor_set_pointer_color": lambda d, _k="cursor", _m="set_pointer_color", _p=["hex_color"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    # -- LockScreenManager --
    "uictl_lockscreen_get_background_mode": lambda d, _k="lock_screen", _m="get_background_mode", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_lockscreen_set_spotlight": lambda d, _k="lock_screen", _m="set_windows_spotlight", _p=[
        "show_fun_facts"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_lockscreen_set_picture": lambda d, _k="lock_screen", _m="set_picture", _p=["image_path"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_lockscreen_get_timeout": lambda d, _k="lock_screen", _m="get_lock_timeout", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_lockscreen_set_timeout": lambda d, _k="lock_screen", _m="set_lock_timeout", _p=[
        "timeout_seconds",
        "require_signin_on_resume",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_lockscreen_get_detailed_status": lambda d, _k="lock_screen", _m="get_show_detailed_status", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_lockscreen_set_detailed_status": lambda d, _k="lock_screen", _m="set_show_detailed_status", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- NotificationManager --
    "uictl_notif_get_enabled": lambda d, _k="notification", _m="get_notifications_enabled", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_notif_set_enabled": lambda d, _k="notification", _m="set_notifications_enabled", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_notif_set_show_on_lock_screen": lambda d, _k="notification", _m="set_show_on_lock_screen", _p=[
        "enabled"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_notif_list_app_ids": lambda d, _k="notification", _m="list_app_ids", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_notif_get_app_settings": lambda d, _k="notification", _m="get_app_settings", _p=["app_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_notif_set_app_enabled": lambda d, _k="notification", _m="set_app_enabled", _p=["app_id", "enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_notif_set_app_sound_enabled": lambda d, _k="notification", _m="set_app_sound_enabled", _p=[
        "app_id",
        "enabled",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_notif_set_app_show_in_action_center": lambda d, _k="notification", _m="set_app_show_in_action_center", _p=[
        "app_id",
        "enabled",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_notif_get_focus_assist_mode": lambda d, _k="notification", _m="get_focus_assist_mode", _p=[]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_notif_set_focus_assist_mode": lambda d, _k="notification", _m="set_focus_assist_mode", _p=[
        "mode",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- WidgetsManager --
    "uictl_widgets_open": lambda d, _k="widgets", _m="open_widgets_board", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "uictl_widgets_close": lambda d, _k="widgets", _m="close_widgets_board", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_widgets_get_open_on_hover": lambda d, _k="widgets", _m="get_open_on_hover", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_widgets_set_open_on_hover": lambda d, _k="widgets", _m="set_open_on_hover", _p=["enabled"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "uictl_widgets_get_allowed": lambda d, _k="widgets", _m="get_widgets_allowed", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "uictl_widgets_set_allowed": lambda d, _k="widgets", _m="set_widgets_allowed", _p=["allowed", "confirm"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
}
