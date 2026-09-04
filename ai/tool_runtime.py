"""
Tool runtime
============
Single shared implementation of "tool name + raw args dict -> JSON result".
Both ai/cloud_models/groq_client.py and ai/local_models/manager.py call
execute_tool_call() instead of each keeping their own copy of the tool
mapping - previously this dict was duplicated verbatim inside the Groq
client, which meant every new tool had to be added in two places (and
easily drifted out of sync). Now there's exactly one place.

Keep this in sync with ai/tools_schema.py (tool definitions the model sees)
and core/executor.py's tool_map (final dispatch to windows/, browser/,
automation/, etc.) - every name here must exist in both.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

from core.executor import execute_tool
from skills.internet.web_tools import WebTools
from storage.cache.usage_tracker import UsageTracker
from search.fact_check import get_fact_check

# Shared WebTools singleton - stateless dispatch, safe to reuse across both
# AI backends and across every turn of a conversation.
_web_tools: Optional[WebTools] = None


def _get_web_tools() -> WebTools:
    global _web_tools
    if _web_tools is None:
        _web_tools = WebTools()
    return _web_tools


def _get_usage_tracker() -> UsageTracker:
    # Deliberately NOT cached: UsageTracker loads its data once at
    # construction time, and UltronGroqClient/local-manager instances each
    # keep their own tracker for incrementing usage as they make calls. A
    # fresh instance here re-reads storage/cache/ultron_usage.json from disk
    # so "get api usage" always reflects the latest totals instead of
    # whatever this module happened to see at import time.
    return UsageTracker()


# name -> (raw_args_dict) -> normalized_kwargs_dict for core.executor.execute_tool
TOOL_ARG_MAP = {
    "list_directory": lambda d: {"path": d.get("path", "~")},
    "find_folder": lambda d: {"folder_name": d.get("folder_name"), "search_path": d.get("search_path", "~")},
    "search_files": lambda d: {"pattern": d.get("pattern"), "search_path": d.get("search_path", "~")},
    "read_file": lambda d: {"file_path": d.get("file_path")},
    "get_file_info": lambda d: {"file_path": d.get("file_path")},
    "run_command": lambda d: {"command": d.get("command", "")},
    "get_system_info": lambda d: {},
    "open_application": lambda d: {"app_name": d.get("app_name")},
    "close_application": lambda d: {"app_name": d.get("app_name")},
    "list_running_apps": lambda d: {},
    "activate_window": lambda d: {"window_title": d.get("window_title")},
    "click_ui_element": lambda d: {"element_name": d.get("element_name"), "window_title": d.get("window_title")},
    "type_into_ui_element": lambda d: {
        "element_name": d.get("element_name"),
        "text": d.get("text", ""),
        "window_title": d.get("window_title"),
    },
    "list_ui_elements": lambda d: {"window_title": d.get("window_title"), "control_type": d.get("control_type")},
    # Vision-LLM fallback for the same "find/click something on screen" job,
    # for targets the accessibility tree above can't see - see vision/vision_llm.py.
    "describe_screen": lambda d: {"question": d.get("question", "Describe what's currently on screen.")},
    # Vision Phase 4: distinct from describe_screen above - see the note in
    # ai/tools_schema.py next to this tool's definition for why the name
    # had to change.
    "describe_screen_regions": lambda d: {"include_objects": d.get("include_objects", True)},
    "locate_on_screen": lambda d: {"target": d.get("target")},
    "click_by_vision": lambda d: {"target": d.get("target"), "double_click": bool(d.get("double_click", False))},
    "open_url": lambda d: {"url": d.get("url")},
    "open_urls": lambda d: {"urls": d.get("urls", [])},
    "list_chrome_tabs": lambda d: {},
    "close_chrome_tab": lambda d: {"tab": d.get("tab", "")},
    "close_chrome_tabs": lambda d: {"tabs": d.get("tabs", [])},
    "scroll_chrome": lambda d: {"direction": d.get("direction", "down"), "amount": d.get("amount", 300)},
    "chrome_navigate": lambda d: {"action": d.get("action", "")},
    "type_in_chrome": lambda d: {"text": d.get("text", "")},
    "chrome_keypress": lambda d: {"key": d.get("key", "enter")},
    "youtube_search": lambda d: {"query": d.get("query", "")},
    "youtube_control": lambda d: {"action": d.get("action", "toggle")},
    "chrome_zoom": lambda d: {"action": d.get("action", "in")},
    "open_file": lambda d: {"file_path": d.get("file_path")},
    "set_volume": lambda d: {"level": d.get("level", 50)},
    "get_volume": lambda d: {},
    "mute": lambda d: {},
    "unmute": lambda d: {},
    "take_screenshot": lambda d: {"filename": d.get("filename")},
    "get_battery_status": lambda d: {},
    "empty_trash": lambda d: {},
    "sleep_display": lambda d: {},
    "create_folder": lambda d: {"folder_path": d.get("folder_path")},
    "create_file": lambda d: {"file_path": d.get("file_path"), "content": d.get("content", "")},
    "write_file": lambda d: {
        "file_path": d.get("file_path"),
        "content": d.get("content", ""),
        "append": d.get("append", False),
    },
    "copy_file": lambda d: {"source": d.get("source"), "destination": d.get("destination")},
    "move_file": lambda d: {"source": d.get("source"), "destination": d.get("destination")},
    "delete_file": lambda d: {"file_path": d.get("file_path")},
    "delete_folder": lambda d: {"folder_path": d.get("folder_path")},
    "get_clipboard": lambda d: {},
    "set_clipboard": lambda d: {"text": d.get("text", "")},
    "get_cpu_ram_usage": lambda d: {},
    "get_ip_address": lambda d: {},
    "lock_screen": lambda d: {},
    "shutdown_pc": lambda d: {"confirm": d.get("confirm", False)},
    "restart_pc": lambda d: {"confirm": d.get("confirm", False)},
    "sign_out": lambda d: {"confirm": d.get("confirm", False)},
    "cancel_shutdown": lambda d: {},
    "get_brightness": lambda d: {},
    "set_brightness": lambda d: {"level": d.get("level", 50)},
    "media_play_pause": lambda d: {},
    "media_next": lambda d: {},
    "media_previous": lambda d: {},
    "media_volume_up": lambda d: {},
    "media_volume_down": lambda d: {},
    "media_mute": lambda d: {},
    "type_text": lambda d: {"text": d.get("text", "")},
    "press_key": lambda d: {"key": d.get("key", "enter")},
    "get_weather": lambda d: {"location": d.get("location", "")},
    "save_note": lambda d: {"text": d.get("text", "")},
    "read_notes": lambda d: {},
    # PDF / Office / Compression
    "extract_pdf_text": lambda d: {"file_path": d.get("file_path", "")},
    "get_pdf_page_count": lambda d: {"file_path": d.get("file_path", "")},
    "merge_pdfs": lambda d: {"file_paths": d.get("file_paths", []), "output_path": d.get("output_path", "")},
    "create_pdf_from_text": lambda d: {
        "file_path": d.get("file_path", ""),
        "text": d.get("text", ""),
        "title": d.get("title", ""),
    },
    "read_docx": lambda d: {"file_path": d.get("file_path", "")},
    "create_docx": lambda d: {
        "file_path": d.get("file_path", ""),
        "content": d.get("content", ""),
        "title": d.get("title", ""),
    },
    "read_xlsx": lambda d: {"file_path": d.get("file_path", ""), "sheet_name": d.get("sheet_name")},
    "create_xlsx": lambda d: {"file_path": d.get("file_path", ""), "rows": d.get("rows", [])},
    "compress_files": lambda d: {"source_path": d.get("source_path", ""), "output_path": d.get("output_path")},
    "extract_archive": lambda d: {"archive_path": d.get("archive_path", ""), "output_dir": d.get("output_dir")},
    # Process management
    "list_processes": lambda d: {"sort_by": d.get("sort_by", "memory"), "limit": d.get("limit", 30)},
    "find_process": lambda d: {"name": d.get("name", "")},
    "kill_process": lambda d: {"name": d.get("name"), "pid": d.get("pid"), "confirm": d.get("confirm", False)},
    "get_process_info": lambda d: {"pid": d.get("pid")},
    # Services / startup / notifications / firewall / defender / explorer / powershell
    "list_services": lambda d: {"filter_status": d.get("filter_status")},
    "get_service_status": lambda d: {"service_name": d.get("service_name", "")},
    "list_startup_programs": lambda d: {},
    "show_notification": lambda d: {
        "title": d.get("title", ""),
        "message": d.get("message", ""),
        "duration": d.get("duration", 5),
    },
    "get_firewall_status": lambda d: {},
    "get_defender_status": lambda d: {},
    "start_defender_scan": lambda d: {},
    "open_explorer_at": lambda d: {"path": d.get("path", "~")},
    "reveal_file_in_explorer": lambda d: {"file_path": d.get("file_path", "")},
    "run_powershell": lambda d: {"script": d.get("script", "")},
    # Edge / Firefox
    "list_edge_tabs": lambda d: {},
    "close_edge_tab": lambda d: {"tab": d.get("tab", "")},
    "scroll_edge": lambda d: {"direction": d.get("direction", "down"), "amount": d.get("amount", 300)},
    "edge_navigate": lambda d: {"action": d.get("action", "")},
    "type_in_edge": lambda d: {"text": d.get("text", "")},
    "list_firefox_tabs": lambda d: {},
    "close_firefox_tab": lambda d: {"tab": d.get("tab", "")},
    "scroll_firefox": lambda d: {"direction": d.get("direction", "down"), "amount": d.get("amount", 300)},
    "firefox_navigate": lambda d: {"action": d.get("action", "")},
    "list_downloads": lambda d: {"limit": d.get("limit", 30)},
    "open_download": lambda d: {"filename": d.get("filename", "")},
    "get_download_history": lambda d: {"browser": d.get("browser", "chrome"), "limit": d.get("limit", 20)},
    # Mouse / macros / workflows
    "mouse_move": lambda d: {"x": d.get("x", 0), "y": d.get("y", 0)},
    "mouse_click": lambda d: {"x": d.get("x"), "y": d.get("y"), "button": d.get("button", "left")},
    "mouse_scroll": lambda d: {"amount": d.get("amount", 0)},
    "start_macro_recording": lambda d: {},
    "stop_macro_recording": lambda d: {"macro_name": d.get("macro_name", "")},
    "play_macro": lambda d: {"macro_name": d.get("macro_name", ""), "speed": d.get("speed", 1.0)},
    "list_macros": lambda d: {},
    "save_workflow": lambda d: {"workflow_name": d.get("workflow_name", ""), "steps": d.get("steps", [])},
    "run_workflow": lambda d: {"workflow_name": d.get("workflow_name", "")},
    "list_workflows": lambda d: {},
    # Memory: facts + similarity search
    "remember_fact": lambda d: {
        "key": d.get("key", ""),
        "value": d.get("value", ""),
        "category": d.get("category", "general"),
    },
    "recall_fact": lambda d: {"key": d.get("key", ""), "category": d.get("category", "general")},
    "search_facts": lambda d: {"query": d.get("query", ""), "category": d.get("category")},
    "forget_fact": lambda d: {"key": d.get("key", ""), "category": d.get("category", "general")},
    "remember_for_search": lambda d: {"text": d.get("text", ""), "category": d.get("category", "general")},
    "search_memory": lambda d: {"query": d.get("query", ""), "top_k": d.get("top_k", 5)},
    # Vision: OCR
    "read_screen_text": lambda d: {},
    # Vision: face / object / UI detection
    "detect_faces_on_screen": lambda d: {},
    "detect_objects_on_screen": lambda d: {"confidence_threshold": d.get("confidence_threshold", 0.4)},
    "find_ui_text_regions": lambda d: {},
    # Coding agent
    "write_code": lambda d: {"spec": d.get("spec", ""), "language": d.get("language")},
    "review_code": lambda d: {"code": d.get("code", "")},
    "fix_code": lambda d: {"code": d.get("code", ""), "error_message": d.get("error_message")},
    "explain_code": lambda d: {"code": d.get("code", "")},
    # App control (skills/app_control/*)
    "find_app": lambda d: {"query": d.get("query", "")},
    "app_status": lambda d: {"app_name": d.get("app_name", "")},
    "restart_app": lambda d: {"app_name": d.get("app_name", "")},
    "minimize_app": lambda d: {"app_name": d.get("app_name", "")},
    "maximize_app": lambda d: {"app_name": d.get("app_name", "")},
    "focus_app": lambda d: {"app_name": d.get("app_name", "")},
    "close_all_by_category": lambda d: {"category": d.get("category", "")},
    "kill_unresponsive_apps": lambda d: {},
    "list_apps_by_category": lambda d: {"category": d.get("category", "")},
    # Window manager
    "list_windows": lambda d: {},
    "get_window_geometry": lambda d: {"window_title": d.get("window_title", "")},
    "move_window": lambda d: {"window_title": d.get("window_title", ""), "x": d.get("x", 0), "y": d.get("y", 0)},
    "resize_window": lambda d: {
        "window_title": d.get("window_title", ""),
        "width": d.get("width", 800),
        "height": d.get("height", 600),
    },
    "snap_window": lambda d: {"window_title": d.get("window_title", ""), "zone": d.get("zone", "left")},
    "minimize_window": lambda d: {"window_title": d.get("window_title", "")},
    "maximize_window": lambda d: {"window_title": d.get("window_title", "")},
    "restore_window": lambda d: {"window_title": d.get("window_title", "")},
    "close_window": lambda d: {"window_title": d.get("window_title", "")},
    "bring_window_to_front": lambda d: {"window_title": d.get("window_title", "")},
    "tile_windows": lambda d: {"window_titles": d.get("window_titles", [])},
    # Virtual desktops
    "list_virtual_desktops": lambda d: {},
    "create_virtual_desktop": lambda d: {},
    "switch_virtual_desktop": lambda d: {"desktop_number": d.get("desktop_number", 1)},
    "switch_next_virtual_desktop": lambda d: {},
    "switch_previous_virtual_desktop": lambda d: {},
    "close_virtual_desktop": lambda d: {},
    "move_window_to_desktop": lambda d: {
        "window_title": d.get("window_title", ""),
        "desktop_number": d.get("desktop_number", 1),
    },
    # Power management
    "sleep_now": lambda d: {},
    "hibernate_now": lambda d: {},
    "list_power_plans": lambda d: {},
    "get_active_power_plan": lambda d: {},
    "set_power_plan": lambda d: {"plan_name": d.get("plan_name", "")},
    "set_sleep_timeout": lambda d: {"minutes": d.get("minutes", 15), "on_battery": d.get("on_battery", False)},
    "set_screen_timeout": lambda d: {"minutes": d.get("minutes", 10), "on_battery": d.get("on_battery", False)},
    "enable_battery_saver": lambda d: {},
    "disable_battery_saver": lambda d: {},
    # Accessibility
    "toggle_narrator": lambda d: {},
    "set_high_contrast": lambda d: {"enabled": d.get("enabled", True)},
    "toggle_magnifier": lambda d: {},
    "set_sticky_keys": lambda d: {"enabled": d.get("enabled", True)},
    "announce": lambda d: {"text": d.get("text", "")},
    # Bookmarks
    "list_bookmarks": lambda d: {"browser": d.get("browser", "chrome")},
    "search_bookmarks": lambda d: {"query": d.get("query", ""), "browser": d.get("browser", "chrome")},
    "add_bookmark": lambda d: {
        "name": d.get("name", ""),
        "url": d.get("url", ""),
        "browser": d.get("browser", "chrome"),
        "folder": d.get("folder", "Bookmarks bar"),
    },
    "delete_bookmark": lambda d: {"name": d.get("name", ""), "browser": d.get("browser", "chrome")},
    # History analysis
    "recent_browser_history": lambda d: {"browser": d.get("browser", "chrome"), "limit": d.get("limit", 30)},
    "most_visited_sites": lambda d: {"browser": d.get("browser", "chrome"), "limit": d.get("limit", 15)},
    "top_browsed_domains": lambda d: {
        "browser": d.get("browser", "chrome"),
        "limit": d.get("limit", 15),
        "days": d.get("days", 30),
    },
    "browsing_activity_by_hour": lambda d: {"browser": d.get("browser", "chrome"), "days": d.get("days", 30)},
    "search_browser_history": lambda d: {
        "query": d.get("query", ""),
        "browser": d.get("browser", "chrome"),
        "limit": d.get("limit", 30),
    },
    # Cross-browser tabs
    "list_all_tabs": lambda d: {},
    "close_tab_in_browser": lambda d: {"tab": d.get("tab", ""), "browser": d.get("browser", "chrome")},
    "close_tabs_matching": lambda d: {"query": d.get("query", "")},
    # Form filler
    "fill_form_field": lambda d: {"value": d.get("value", ""), "press_tab_after": d.get("press_tab_after", True)},
    "fill_form_sequence": lambda d: {"values": d.get("values", [])},
    "submit_form": lambda d: {},
    "save_form_profile": lambda d: {"profile_name": d.get("profile_name", ""), "fields": d.get("fields", {})},
    "autofill_form": lambda d: {"profile_name": d.get("profile_name", ""), "field_order": d.get("field_order", [])},
    # RPA
    "rpa_start_recording": lambda d: {},
    "rpa_stop_recording": lambda d: {"script_name": d.get("script_name", "")},
    # Verification-pass fix: rpa_add_step/rpa_insert_step/rpa_delete_step
    # already had a real, correct handler in core/executor.py's dict
    # (RPARecorder.add_step / RPAEditor.insert_step / RPAEditor.delete_step)
    # but no entry here in TOOL_ARG_MAP - execute_tool_call() checks this
    # dict BEFORE ever reaching core/executor.py, so all 3 returned
    # "Unknown tool" no matter how correct the backend was.
    "rpa_add_step": lambda d: {"step_type": d.get("step_type", ""), **{k: v for k, v in d.items() if k != "step_type"}},
    "rpa_insert_step": lambda d: {
        "script_name": d.get("script_name", ""),
        "index": d.get("index", 0),
        "step": d.get("step", {}),
    },
    "rpa_play": lambda d: {
        "script_name": d.get("script_name", ""),
        "speed": d.get("speed", 1.0),
        "loop": d.get("loop", 1),
    },
    "rpa_dry_run": lambda d: {"script_name": d.get("script_name", "")},
    "rpa_list_scripts": lambda d: {},
    "rpa_delete_step": lambda d: {"script_name": d.get("script_name", ""), "step_id": d.get("step_id", "")},
    "rpa_delete_script": lambda d: {"script_name": d.get("script_name", "")},
    # Triggers
    "watch_file": lambda d: {
        "path": d.get("path", ""),
        "tool_name": d.get("tool_name"),
        "arguments": d.get("arguments", {}),
        "events": d.get("events"),
        "recursive": d.get("recursive", False),
    },
    "stop_watching_file": lambda d: {"watch_id": d.get("watch_id", "")},
    "list_file_watches": lambda d: {},
    "add_daily_trigger": lambda d: {
        "hour": d.get("hour", 9),
        "minute": d.get("minute", 0),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "days": d.get("days"),
        "label": d.get("label", ""),
    },
    "add_interval_trigger": lambda d: {
        "interval_seconds": d.get("interval_seconds", 3600),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "label": d.get("label", ""),
    },
    "remove_time_trigger": lambda d: {"trigger_id": d.get("trigger_id", "")},
    "list_time_triggers": lambda d: {},
    "on_battery_threshold": lambda d: {
        "below_percent": d.get("below_percent", 20),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "only_when_discharging": d.get("only_when_discharging", True),
        "label": d.get("label", ""),
    },
    "on_process_start_trigger": lambda d: {
        "process_name": d.get("process_name", ""),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "label": d.get("label", ""),
    },
    "on_process_stop_trigger": lambda d: {
        "process_name": d.get("process_name", ""),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "label": d.get("label", ""),
    },
    "list_system_triggers": lambda d: {},
    "remove_system_trigger": lambda d: {"trigger_id": d.get("trigger_id", "")},
    # Conditions & loops
    "evaluate_condition": lambda d: {"condition": d.get("condition", {})},
    "run_if_condition": lambda d: {
        "condition": d.get("condition", {}),
        "then_step": d.get("then_step", {}),
        "else_step": d.get("else_step"),
    },
    "loop_repeat": lambda d: {
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "times": d.get("times", 1),
        "delay_seconds": d.get("delay_seconds", 0.0),
    },
    "loop_while": lambda d: {
        "condition": d.get("condition", {}),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "max_iterations": d.get("max_iterations", 100),
        "delay_seconds": d.get("delay_seconds", 1.0),
    },
    "loop_for_each": lambda d: {
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "items": d.get("items", []),
        "item_arg_name": d.get("item_arg_name", "item"),
    },
    # --- Pre-existing gap fix: these 33 tools were already defined in
    # ai/tools_schema.py (so the model could see and call them) AND already
    # dispatched in core/executor.py's tool_map, but had NO entry here in
    # TOOL_ARG_MAP - so execute_tool_call() (what both AI backends actually
    # call) hit "Unknown tool" for every one of them. Adding them now so the
    # calendar/todo/health/security/email/memory/RAG/plugin/workflow/task
    # tools actually work end to end, not just on paper.
    "save_advanced_workflow": lambda d: {"name": d.get("name", ""), "steps": d.get("steps", [])},
    "run_advanced_workflow": lambda d: {
        "name": d.get("name", ""),
        "stop_on_error": d.get("stop_on_error", True),
        "run_in_background": d.get("run_in_background", False),
    },
    "list_advanced_workflows": lambda d: {},
    "get_task_status": lambda d: {"task_id": d.get("task_id", "")},
    "list_background_tasks": lambda d: {"status": d.get("status")},
    "add_calendar_event": lambda d: {
        "title": d.get("title", ""),
        "start_time": d.get("start_time", ""),
        "end_time": d.get("end_time"),
        "location": d.get("location", ""),
        "notes": d.get("notes", ""),
    },
    "list_calendar_events": lambda d: {"start_time": d.get("start_time"), "end_time": d.get("end_time")},
    "upcoming_calendar_events": lambda d: {"within_hours": d.get("within_hours", 24)},
    "delete_calendar_event": lambda d: {"event_id": d.get("event_id", "")},
    "add_todo": lambda d: {"text": d.get("text", ""), "priority": d.get("priority", "normal"), "due": d.get("due")},
    "list_todos": lambda d: {"include_done": d.get("include_done", False)},
    "complete_todo": lambda d: {"todo_id": d.get("todo_id", "")},
    "delete_todo": lambda d: {"todo_id": d.get("todo_id", "")},
    "log_water": lambda d: {"ml": d.get("ml", 0)},
    "log_sleep": lambda d: {"hours": d.get("hours", 0), "note": d.get("note", "")},
    "log_exercise": lambda d: {"minutes": d.get("minutes", 0), "note": d.get("note", "")},
    "health_daily_summary": lambda d: {},
    "check_password_strength": lambda d: {"password": d.get("password", "")},
    "generate_secure_password": lambda d: {"length": d.get("length", 16), "symbols": d.get("symbols", True)},
    "audit_file_permissions": lambda d: {"path": d.get("path", "")},
    "send_email": lambda d: {
        "to": d.get("to", ""),
        "subject": d.get("subject", ""),
        "body": d.get("body", ""),
        "cc": d.get("cc"),
    },
    "read_inbox": lambda d: {"limit": d.get("limit", 10), "unread_only": d.get("unread_only", False)},
    "search_emails": lambda d: {"query": d.get("query", ""), "limit": d.get("limit", 10)},
    "record_event": lambda d: {"event": d.get("event", ""), "context": d.get("context", ""), "tags": d.get("tags", "")},
    "recall_recent_events": lambda d: {"limit": d.get("limit", 20)},
    "define_concept": lambda d: {"concept": d.get("concept", ""), "definition": d.get("definition", "")},
    "recall_concept": lambda d: {"concept": d.get("concept", "")},
    "log_mood": lambda d: {
        "emotion": d.get("emotion", ""),
        "intensity": d.get("intensity", 3),
        "note": d.get("note", ""),
    },
    "get_mood_trend": lambda d: {"days": d.get("days", 7)},
    "rag_answer": lambda d: {"question": d.get("question", ""), "top_k": d.get("top_k", 5)},
    "reason_deeply": lambda d: {"question": d.get("question", ""), "max_subquestions": d.get("max_subquestions", 5)},
    "list_available_plugins": lambda d: {},
    "install_plugin": lambda d: {"name": d.get("name", "")},
    # --- Gap fix #2: another 16 tools already defined in ai/tools_schema.py
    # (so the model could see and call them) AND already dispatched in
    # core/executor.py's tool_map, but had NO entry here - same bug class
    # as the 33-tool gap fix above, just missed in that pass. Without these,
    # execute_tool_call() returned "Unknown tool" for every one of them even
    # though the real backend implementations (voice/, vision/, windows/,
    # browser/) exist and work.
    "detect_form_fields": lambda d: {},
    "parse_diagram": lambda d: {},
    "read_handwriting": lambda d: {"file_path": d.get("file_path")},
    "add_voice_command": lambda d: {
        "phrase": d.get("phrase", ""),
        "tool_name": d.get("tool_name", ""),
        "arguments": d.get("arguments", {}),
        "label": d.get("label", ""),
    },
    "remove_voice_command": lambda d: {"phrase": d.get("phrase", "")},
    "list_voice_commands": lambda d: {},
    "enroll_speaker_voice": lambda d: {"name": d.get("name", ""), "duration": d.get("duration", 4.0)},
    "identify_speaker_from_mic": lambda d: {"duration": d.get("duration", 4.0)},
    "list_enrolled_speakers": lambda d: {},
    "forget_speaker": lambda d: {"name": d.get("name", "")},
    "detect_voice_emotion": lambda d: {"duration": d.get("duration", 4.0)},
    "analyze_text_sentiment": lambda d: {"text": d.get("text", "")},
    "set_tts_engine": lambda d: {"engine": d.get("engine", "edge")},
    "list_voice_engines": lambda d: {},
    "get_disk_usage": lambda d: {"drive": d.get("drive")},
    "youtube_play": lambda d: {"query": d.get("query", "")},
    # call_phone was declared in ai/tools_schema.py and wired in
    # core/executor.py's tool_map, but had no entry here - meaning the
    # real model-facing path (execute_tool_from_dict -> ActionPipeline ->
    # execute_tool_call) rejected every call with "Unknown tool: call_phone"
    # before ever reaching core/executor.py, same bug class as the 16
    # missing entries found and patched in the Phase 1-29 audit. It's
    # also destructive (core/permissions.py's DESTRUCTIVE_TOOLS), so it
    # goes through ActionPipeline's confirmation gate before this map is
    # even consulted - normalization here only needs to pass the args
    # through as-is.
    "call_phone": lambda d: {"number": d.get("number", ""), "name": d.get("name"), "confirm": d.get("confirm", False)},
    "add_contact": lambda d: {
        "name": d.get("name", ""),
        "phone": d.get("phone", ""),
        "email": d.get("email", ""),
        "notes": d.get("notes", ""),
    },
    "find_contact": lambda d: {"name": d.get("name", "")},
    "list_contacts": lambda d: {},
    "delete_contact": lambda d: {"name": d.get("name", "")},
    "google_calendar_list_events": lambda d: {"num": d.get("num", 5)},
    "google_calendar_create_event": lambda d: {
        "summary": d.get("summary", ""),
        "start_iso": d.get("start_iso", ""),
        "end_iso": d.get("end_iso", ""),
        "description": d.get("description", ""),
    },
    "post_to_social": lambda d: {"message": d.get("message", ""), "platforms": d.get("platforms")},
}


# Tools handled directly here instead of through core.executor (they need
# an object with local state - a requests session, a usage-tracker file
# handle - rather than being a stateless windows/ facade call).
def _fact_check_claim(args: Dict) -> Dict:
    """fact_check_claim tool: what published fact-checkers have said about
    a claim (Google Fact Check Tools API - see PHASE_18_5_SEARCH_ENGINE/
    SEARCH/fact_check.py). Needs GOOGLE_SEARCH_API_KEY; if it's not
    configured, says so plainly instead of silently returning nothing so
    the model doesn't mistake "no key" for "no fact-checkers found this"."""
    fc = get_fact_check()
    if not fc.is_available():
        return {
            "success": False,
            "error": "Fact-check backend not configured (set GOOGLE_SEARCH_API_KEY).",
        }
    claims = fc.check_claim(args.get("claim", ""))
    return {"success": True, "claims": claims, "count": len(claims)}


def _search_offline_knowledge(args: Dict) -> Dict:
    from knowledge_base.offline_wiki import search_offline

    return search_offline(args.get("query", ""))


_DIRECT_HANDLERS = {
    "search_internet": lambda args: _get_web_tools().search_internet(args.get("query", "")),
    "read_url": lambda args: _get_web_tools().read_url(args.get("url", "")),
    "search_offline_knowledge": _search_offline_knowledge,
    "fact_check_claim": _fact_check_claim,
    "get_api_usage": lambda args: _get_usage_tracker().get_usage_summary(),
}

# New skills & integrations (skills/email, skills/calendar, skills/web,
# skills/data, skills/communication, integration/*) - see ai/new_skills_tools.py.
# Merged the same way as the three built-ins above: stateless dispatch,
# lazy singletons, dict-in/dict-out.
from ai.new_skills_tools import NEW_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(NEW_DIRECT_HANDLERS)

# Phase 27: movie assistant (modules/movie_assistant/) - see
# ai/movie_assistant_tools.py. Same merge pattern as NEW_DIRECT_HANDLERS
# above.
from ai.movie_assistant_tools import MOVIE_ASSISTANT_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(MOVIE_ASSISTANT_DIRECT_HANDLERS)

# Phase 6: app automations (apps/*) - see ai/apps_tools.py. Same merge
# pattern as NEW_DIRECT_HANDLERS above.
from ai.apps_tools import APPS_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(APPS_DIRECT_HANDLERS)

# Phase 7: browser data automations - see ai/browser_tools.py. Same merge
# pattern as APPS_DIRECT_HANDLERS above.
from ai.browser_tools import BROWSER_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(BROWSER_DIRECT_HANDLERS)

# Verification-pass fix: wires skills/utilities/tools.py's 19 real
# actions (text/unit/date/hash/random helpers) into the tool-calling
# loop - see ai/utility_tools_wire.py. Same merge pattern as the three
# updates above.
from ai.utility_tools_wire import UTILITY_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(UTILITY_DIRECT_HANDLERS)

# Verification-pass fix: 18 PHASE_18_9_2_SELF_MANAGEMENT (HEAL +
# PROACTIVE) tools and 9 PHASE_18_6_AI_AGENTS persona-agent tools each
# already had a tools_schema.py entry but no dispatch entry here, so the
# model got "Unknown tool" for all 27 despite working backends existing -
# see ai/self_management_tools.py and ai/agents_tools.py. Same merge
# pattern as the updates above.
from ai.self_management_tools import SELF_MANAGEMENT_DIRECT_HANDLERS  # noqa: E402
from ai.agents_tools import AGENTS_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SELF_MANAGEMENT_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(AGENTS_DIRECT_HANDLERS)

# Verification-pass fix: agents/vision_agent.py's 5 unique capabilities
# (named-face enroll/recognize, icon-button detection, screen recording)
# - see ai/vision_agent_tools.py for why these 5 specifically and not
# the 4 that already work through a different, existing tool.
from ai.vision_agent_tools import VISION_AGENT_DIRECT_HANDLERS  # noqa: E402
from ai.visual_automator_tools import VISUAL_AUTOMATOR_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(VISION_AGENT_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(VISUAL_AUTOMATOR_DIRECT_HANDLERS)

# Verification-pass fix: get_admin_status/relaunch_as_admin - see
# ai/admin_tools.py.
from ai.admin_tools import ADMIN_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(ADMIN_DIRECT_HANDLERS)

# Deep-audit fix: same 3 files as in ai/tools_schema.py - implemented,
# working handlers that were never merged into _DIRECT_HANDLERS, so even if
# the model had guessed the tool name, dispatch would have failed.
from ai.phase30_new_tools import PHASE30_DIRECT_HANDLERS  # noqa: E402
from ai.phase30_advanced_tools import PHASE30_ADVANCED_DIRECT_HANDLERS  # noqa: E402
from ai.image_display_tools import IMAGE_DISPLAY_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(PHASE30_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(PHASE30_ADVANCED_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(IMAGE_DISPLAY_DIRECT_HANDLERS)

# Deep-audit fix, item #4 (safe batch) - see ai/phase30_extended_tools.py
from ai.phase30_extended_tools import PHASE30_EXTENDED_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(PHASE30_EXTENDED_DIRECT_HANDLERS)

# Deep-audit fix, item #4 (gated batch) - see ai/phase30_gated_tools.py.
# Handlers are always registered (so a stray call gets a clean "disabled"
# message instead of "unknown tool"), but the schema in tools_schema.py
# only advertises them when their env flag is on.
from ai.phase30_gated_tools import PHASE30_GATED_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(PHASE30_GATED_DIRECT_HANDLERS)

# Camera+vision skill (skills/vision/) - see ai/vision_skill_tools.py.
# Same "wire it up now, not after an audit finds it missing" reasoning as
# every _DIRECT_HANDLERS.update() above.
from ai.vision_skill_tools import VISION_SKILL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(VISION_SKILL_DIRECT_HANDLERS)

# Change-detection skill (skills/vision/change_detector.py) - see
# ai/change_detection_tools.py.
from ai.change_detection_tools import CHANGE_DETECTION_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(CHANGE_DETECTION_DIRECT_HANDLERS)

# Autonomous internet-learning controls - see ai/autonomous_learning_tools.py.
from ai.autonomous_learning_tools import AUTOLEARN_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(AUTOLEARN_DIRECT_HANDLERS)

# system_control/system_config/*: registry manager+backup, env vars,
# system properties, device manager control, Windows Update - see
# ai/system_config_tools.py. Same merge pattern as every
# _DIRECT_HANDLERS.update() above.
from ai.system_config_tools import SYSTEM_CONFIG_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SYSTEM_CONFIG_DIRECT_HANDLERS)

# system_control/process/*: startup manager, background/running processes,
# native Windows Task Scheduler - see ai/process_control_tools.py. Same
# merge pattern as every _DIRECT_HANDLERS.update() above.
from ai.process_control_tools import PROCESS_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(PROCESS_CONTROL_DIRECT_HANDLERS)

# system_control/files/*: encryption, permissions, network sharing, sync,
# backup/recovery - see ai/file_control_tools.py. Same merge pattern as
# every _DIRECT_HANDLERS.update() above.
from ai.file_control_tools import FILE_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(FILE_CONTROL_DIRECT_HANDLERS)


# system_control/network/*: Wi-Fi, Ethernet, VPN control - see
# ai/network_control_tools.py. Same merge pattern as every
# _DIRECT_HANDLERS.update() above.
from ai.network_control_tools import NETWORK_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(NETWORK_CONTROL_DIRECT_HANDLERS)


# system_control/security/*: Defender, all-registered-AV status,
# ransomware/Controlled-Folder-Access, BitLocker, local user accounts,
# password/lockout policy - see ai/security_control_tools.py. Same
# merge pattern as every _DIRECT_HANDLERS.update() above.
from ai.security_control_tools import SECURITY_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SECURITY_CONTROL_DIRECT_HANDLERS)


# system_control/ui/*: theme/dark-mode, accent color, taskbar, Start
# menu, mouse cursor, lock screen, notifications/Focus Assist, Widgets
# board - see ai/ui_control_tools.py. Same merge pattern as every
# _DIRECT_HANDLERS.update() above.
from ai.ui_control_tools import UI_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(UI_CONTROL_DIRECT_HANDLERS)

# system_control/automation/*: saved PowerShell/batch script libraries,
# native (USB/display/power-source/event-log) triggers, native job
# pipelines, system macros, and recurring backup jobs - see
# ai/automation_control_tools.py. Same merge pattern as every
# _DIRECT_HANDLERS.update() above.
from ai.automation_control_tools import AUTOMATION_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(AUTOMATION_CONTROL_DIRECT_HANDLERS)


# system_control/storage/*: disk/partition management, volume
# formatting and filesystem control - see ai/storage_control_tools.py.
# Same merge pattern as every _DIRECT_HANDLERS.update() above.
from ai.storage_control_tools import STORAGE_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(STORAGE_CONTROL_DIRECT_HANDLERS)


# system_control/applications/*: installed-application lifecycle
# (package discovery/install, uninstall, updates, per-app compatibility
# settings, appdata backup, cache cleanup) - see
# ai/application_control_tools.py. Same merge pattern as every
# _DIRECT_HANDLERS.update() above.
from ai.application_control_tools import APPLICATION_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(APPLICATION_CONTROL_DIRECT_HANDLERS)


# system_control/monitoring/*: deep Windows OS instrumentation -
# temperature, event log, reliability index, per-process resource I/O,
# adapter link health, disk health, battery wear, startup/boot impact,
# OS-recorded crash history, and the combined performance report - see
# ai/monitoring_control_tools.py. Same merge pattern as every
# _DIRECT_HANDLERS.update() above.
from ai.monitoring_control_tools import MONITORING_CONTROL_DIRECT_HANDLERS  # noqa: E402
from ai.hardware_extra_control_tools import HARDWARE_EXTRA_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(MONITORING_CONTROL_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(HARDWARE_EXTRA_DIRECT_HANDLERS)


# system_control/special/*: face recognition device control,
# gesture-to-action bindings, predictive-action approval, unified
# context snapshot + rules, self-optimization passes, emergency/panic
# mode, habit-to-automation bridge, multi-user profile linking, and
# scoped remote-access grants - see ai/special_control_tools.py. Same
# merge pattern as every _DIRECT_HANDLERS.update() above.
from ai.special_control_tools import SPECIAL_CONTROL_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SPECIAL_CONTROL_DIRECT_HANDLERS)

# ai_supercharger/, translation_engine/, entertainment_engine/,
# predictive_mind/, decision_engine_2.0/, advanced_personality/,
# empathy_engine/, language_generation/, penetration_testing/,
# threat_hunting/ - see ai/supercharger_tools.py's own docstring.
from ai.supercharger_tools import SUPERCHARGER_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SUPERCHARGER_DIRECT_HANDLERS)

from ai.cognitive_tools import COGNITIVE_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(COGNITIVE_DIRECT_HANDLERS)

from ai.agent_tools import AGENT_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(AGENT_DIRECT_HANDLERS)

from ai.skill_executor_tools import SKILL_EXECUTOR_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SKILL_EXECUTOR_DIRECT_HANDLERS)

# networking/, perception/, scenarios/, scheduler/ - four dormant packages
# wired this task. Same merge pattern as every _DIRECT_HANDLERS.update()
# above. See ai/tools_schema.py's matching comment and each ai/*_tools.py
# module's own docstring.
from ai.networking_tools import NETWORKING_DIRECT_HANDLERS  # noqa: E402
from ai.perception_tools import PERCEPTION_DIRECT_HANDLERS  # noqa: E402
from ai.scenarios_tools import SCENARIOS_DIRECT_HANDLERS  # noqa: E402
from ai.scheduler_tools import SCHEDULER_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(NETWORKING_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(PERCEPTION_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(SCENARIOS_DIRECT_HANDLERS)
_DIRECT_HANDLERS.update(SCHEDULER_DIRECT_HANDLERS)


# ============================================================================
# ULTRON BUG FIX: 44 "P1-P5 Engine Tools" declared in ai/tools_schema.py
# (so the AI model can see and call them) and already correctly implemented
# in core/executor.py's tool_map, but MISSING from ai/tool_runtime.py's
# TOOL_ARG_MAP. Because execute_tool_call() checks TOOL_ARG_MAP BEFORE ever
# reaching core/executor.py, every one of these 44 tools currently returns
# {"error": "Unknown tool: <name>"} no matter how correct the backend is -
# this is the exact same bug class already fixed once before for a
# different batch of 33 tools (see the comment above this block in
# tool_runtime.py). This is that same fix, applied to the newer P1-P5 batch.
#
# HOW TO APPLY:
#   Open ai/tool_runtime.py, find the line:  TOOL_ARG_MAP = {
#   Paste this entire ENGINE_TOOLS_ARG_MAP dict's contents in right after
#   the opening brace (or anywhere inside the TOOL_ARG_MAP dict literal),
#   OR simpler: just add one line right after the TOOL_ARG_MAP dict closes:
#       TOOL_ARG_MAP.update(ENGINE_TOOLS_ARG_MAP)
#   with this whole block pasted above that line.
# ============================================================================

ENGINE_TOOLS_ARG_MAP = {
    # --- P1: Mission Manager ---
    "create_mission": lambda d: {
        "title": d.get("title", ""),
        "description": d.get("description", ""),
        "context": d.get("context"),
    },
    "checkpoint_mission": lambda d: {
        "mission_id": d.get("mission_id", ""),
        "note": d.get("note", ""),
        "state": d.get("state"),
    },
    "list_active_missions": lambda d: {},
    "get_resumable_mission": lambda d: {},
    "resume_mission": lambda d: {"mission_id": d.get("mission_id", "")},
    "pause_mission": lambda d: {"mission_id": d.get("mission_id", "")},
    "complete_mission": lambda d: {"mission_id": d.get("mission_id", "")},
    "abandon_mission": lambda d: {"mission_id": d.get("mission_id", "")},
    # --- P1: Tool Chain Optimizer ---
    "rank_tool_candidates": lambda d: {"candidates": d.get("candidates", [])},
    "optimize_tool_chain": lambda d: {"tools": d.get("tools", [])},
    "get_tool_reliability_report": lambda d: {"limit": d.get("limit", 20)},
    # --- P1: Capability Isolation ---
    "check_capability_access": lambda d: {"tool_name": d.get("tool_name", ""), "arguments": d.get("arguments", {})},
    "set_isolation_profile": lambda d: {"profile": d.get("profile", "")},
    "get_isolation_policy": lambda d: {"profile": d.get("profile")},
    "set_capability_scope_policy": lambda d: {
        "profile": d.get("profile", ""),
        "scope": d.get("scope", ""),
        "mode": d.get("mode", ""),
    },
    # --- P2: Evidence Ledger / Claim Verification ---
    "log_claim_check": lambda d: {
        "claim": d.get("claim", ""),
        "verdict": d.get("verdict", "unverified"),
        "confidence": d.get("confidence", 0.0),
        "evidence": d.get("evidence"),
        "context": d.get("context", ""),
    },
    "record_evidence_outcome": lambda d: {
        "entry_id": d.get("entry_id", ""),
        "outcome": d.get("outcome", ""),
        "note": d.get("note", ""),
    },
    "why_did_you_believe": lambda d: {"claim": d.get("claim", "")},
    "get_source_reliability": lambda d: {"source": d.get("source", "")},
    "get_recent_evidence_entries": lambda d: {"limit": d.get("limit", 20)},
    "get_untrustworthy_sources": lambda d: {},
    # --- P2: Failure Pattern Detector ---
    "check_tool_failure_risk": lambda d: {"tool_name": d.get("tool_name", "")},
    "get_failure_patterns": lambda d: {"tool_name": d.get("tool_name"), "limit": d.get("limit", 20)},
    "get_failure_pattern_report": lambda d: {"limit": d.get("limit", 20)},
    # --- P3: Knowledge OS ---
    # Renamed from "remember_fact" (collided with the simple key/value
    # memory tool at line 174) to "remember_subject_fact" - needs its own
    # arg-map entry now, it can no longer ride on that other tool's.
    "remember_subject_fact": lambda d: {
        "subject": d.get("subject", ""),
        "fact_text": d.get("fact_text", ""),
        "predicate": d.get("predicate", "is"),
        "source": d.get("source", "user"),
        "confidence": d.get("confidence", 0.8),
    },
    "get_unified_knowledge_view": lambda d: {"subject": d.get("subject", "")},
    "search_knowledge": lambda d: {"query": d.get("query", ""), "limit": d.get("limit", 10)},
    "get_knowledge_freshness_report": lambda d: {"max_age_days": d.get("max_age_days", 30)},
    # --- P3: Resource-Aware Execution Engine ---
    "recommend_execution_tier": lambda d: {
        "task_type": d.get("task_type", ""),
        "estimated_cost": d.get("estimated_cost"),
    },
    "track_task_resource_cost": lambda d: {
        "task_type": d.get("task_type", ""),
        "duration_ms": d.get("duration_ms", 0),
        "cpu_before": d.get("cpu_before", 0),
        "cpu_after": d.get("cpu_after", 0),
        "mem_before": d.get("mem_before", 0),
        "mem_after": d.get("mem_after", 0),
    },
    "get_resource_intelligence_report": lambda d: {},
    # --- P4: Tool Benchmarking & Reliability Scoring ---
    "record_tool_benchmark": lambda d: {
        "tool_name": d.get("tool_name", ""),
        "duration_ms": d.get("duration_ms", 0),
        "success": d.get("success", True),
    },
    "get_tool_benchmark": lambda d: {"tool_name": d.get("tool_name", "")},
    "get_tool_benchmark_report": lambda d: {"limit": d.get("limit", 20)},
    "get_degrading_tools": lambda d: {},
    # --- P4: Conflict Resolution Engine ---
    "detect_source_conflict": lambda d: {
        "subject": d.get("subject", ""),
        "claim_a": d.get("claim_a", ""),
        "source_a": d.get("source_a", ""),
        "claim_b": d.get("claim_b", ""),
        "source_b": d.get("source_b", ""),
    },
    "auto_resolve_conflict": lambda d: {"conflict_id": d.get("conflict_id", "")},
    "manual_resolve_conflict": lambda d: {
        "conflict_id": d.get("conflict_id", ""),
        "resolved_source": d.get("resolved_source", ""),
        "note": d.get("note", ""),
    },
    "list_open_conflicts": lambda d: {"subject": d.get("subject")},
    "get_conflict_report": lambda d: {"limit": d.get("limit", 20)},
    # --- P5: Personal Workflow Graph & Automation Discovery ---
    "register_workflow_graph_node": lambda d: {"name": d.get("name", ""), "tools_used": d.get("tools_used", [])},
    "link_workflow_sequence": lambda d: {"workflow_a": d.get("workflow_a", ""), "workflow_b": d.get("workflow_b", "")},
    "discover_automation_opportunities": lambda d: {"min_weight": d.get("min_weight", 2)},
    "get_workflow_graph_neighbors": lambda d: {"name": d.get("name", "")},
    "get_workflow_graph_summary": lambda d: {},
}

TOOL_ARG_MAP.update(ENGINE_TOOLS_ARG_MAP)


def execute_tool_call(tool_name: str, arguments: Dict) -> str:
    """Execute a single tool call and return a JSON string result.
    Identical behavior regardless of which AI backend (cloud or local)
    produced the tool call."""
    if not tool_name:
        return json.dumps({"error": "No tool specified"})

    if tool_name in _DIRECT_HANDLERS:
        try:
            return json.dumps(_DIRECT_HANDLERS[tool_name](arguments))
        except Exception as e:
            # New skills/integrations can raise before reaching their own
            # try/except (e.g. a missing optional dependency like selenium,
            # or FormFiller's __init__ failing fast) - never let that crash
            # the whole tool-calling loop; report it like any other tool error.
            _report_to_runtime_patcher(tool_name, e)
            return json.dumps({"success": False, "error": str(e)})

    if tool_name not in TOOL_ARG_MAP:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        normalized_args = TOOL_ARG_MAP[tool_name](arguments)
        return execute_tool(tool_name, normalized_args)
    except Exception as e:
        # Same guarantee as the _DIRECT_HANDLERS branch above: a raise
        # anywhere inside core.executor.execute_tool() or the underlying
        # skill/agent (missing hardware dep, bad state, network failure,
        # anything) must never kill the whole tool-calling loop - found via
        # verify_all_tools.py, which showed enroll_speaker_voice /
        # identify_speaker_from_mic / detect_voice_emotion propagating a
        # raw RuntimeError all the way up when PyAudio isn't installed.
        # core.executor.execute_tool() itself has no try/except around its
        # tool_map[tool_name](arguments) call, so this is the one place
        # that guards every TOOL_ARG_MAP-routed tool at once.
        _report_to_runtime_patcher(tool_name, e)
        return json.dumps({"success": False, "error": str(e)})


def _report_to_runtime_patcher(tool_name: str, error: Exception) -> None:
    """Feeds every tool-execution crash into self_evolution/runtime_patcher.py
    (gated by ULTRON_RUNTIME_SELF_PATCH_ENABLED - off by default). Fire-and-
    forget: record_error() never raises on its own, and this wrapper adds
    another try/except on top so a reporting bug can never affect the actual
    error response already built above."""
    try:
        if os.getenv("ULTRON_RUNTIME_SELF_PATCH_ENABLED", "false").strip().lower() not in ("1", "true", "yes", "on"):
            return
        from self_evolution.runtime_patcher import get_runtime_patcher

        get_runtime_patcher().record_error(tool_name, error)
    except Exception:
        pass


def execute_tool_from_dict(tool_dict: Dict) -> str:
    """Entry point every AI backend actually calls (groq_client.py,
    deepseek_client.py, nvidia_client.py, gemini_client.py,
    openrouter_client.py) - despite the historical "legacy" framing,
    this is the live path for every tool call the model makes, so this
    is where the permission/confirmation gate belongs, not a second
    copy in each of the five client files.

    Routes through core.action_pipeline.ActionPipeline so every call
    gets: (a) a check against core.permissions.PermissionGate's
    DESTRUCTIVE_TOOLS list (confirmation required, surfaced back to the
    model as needs_confirmation rather than silently executing), and
    (b) an audit trail via unified_context/event_bus. The actual
    dispatch, once permitted, is still execute_tool_call() below -
    ActionPipeline has no separate copy of tool logic, it only gates.
    """
    tool_dict = dict(tool_dict)
    tool_name = tool_dict.pop("tool", None)
    if not tool_name:
        return json.dumps({"error": "No tool specified"})

    try:
        from core.action_pipeline import get_action_pipeline
        from core.capability_registry import get_capability_registry

        registry = get_capability_registry()
        registry.bootstrap()  # idempotent - registers the current tools_schema.py registry
        if not registry.has(tool_name):
            # Not in tools_schema.py (shouldn't happen for a model-issued
            # call, but don't let an unknown/renamed tool silently die
            # here) - fall back to direct dispatch, same as before this
            # change, rather than returning a confusing pipeline error.
            return execute_tool_call(tool_name, tool_dict)

        # NOTE: .get(), deliberately not .pop(). Popping "confirm" here
        # used to strip it out of `tool_dict` before it reached
        # ActionPipeline -> execute_tool_call -> TOOL_ARG_MAP -> the
        # underlying tool - so every destructive tool with its own
        # inline `if not confirm:` check (shutdown_pc, restart_pc,
        # sign_out, kill_process, call_phone, ...) would see confirm=False
        # and refuse EVERY time, even immediately after this same gate
        # had just accepted confirmed=True and approved the call. Central
        # gate and each tool's own belt-and-suspenders check both need to
        # see the same value, so it has to survive in the dict that gets
        # passed onward.
        confirmed = bool(tool_dict.get("confirm", False))
        outcome = get_action_pipeline().run(tool_name, tool_dict, confirmed=confirmed)
    except Exception as e:
        # FAIL-CLOSED for destructive tools: if the security/permission
        # pipeline itself breaks (bug, import error, anything) while
        # handling a tool on PermissionGate.DESTRUCTIVE_TOOLS, we must
        # NOT silently fall back to direct execution - that would let a
        # broken gate become a way to skip confirmation on shutdown_pc,
        # delete_file, run_command, etc. Deny instead, and surface why.
        from core.permissions import PermissionGate

        if tool_name in PermissionGate.DESTRUCTIVE_TOOLS:
            from core.logger import get_logger

            get_logger("ultron.tool_runtime").error(
                f"SECURITY_GATE_UNAVAILABLE: pipeline raised {type(e).__name__} "
                f"while gating destructive tool '{tool_name}' - denying rather than "
                f"falling back to unprotected execution."
            )
            return json.dumps(
                {
                    "success": False,
                    "error": f"'{tool_name}' is a destructive action and the security "
                    f"gate that checks it is currently unavailable "
                    f"({type(e).__name__}). Denying by default - please retry; "
                    f"if this persists, report it as a bug rather than working "
                    f"around it.",
                    "security_gate_unavailable": True,
                }
            )
        # Non-destructive tools: the gate itself must never be the reason
        # a harmless tool call fails - fall back to direct dispatch, same
        # as before, since there's no confirmation/permission requirement
        # to bypass here.
        return execute_tool_call(tool_name, tool_dict)

    if outcome.get("category") == "needs_confirmation":
        return json.dumps(
            {
                "success": False,
                "error": f"'{tool_name}' is a destructive action and requires confirmation. "
                f"Ask the user to confirm, then resend this exact tool call with confirm: true.",
                "needs_confirmation": True,
            }
        )
    if outcome.get("category") == "permission_denied":
        return json.dumps({"success": False, "error": f"'{tool_name}' requires elevated permission."})
    if outcome.get("category") in ("isolation_denied", "isolation_ask"):
        return json.dumps(
            {
                "success": False,
                "error": f"'{tool_name}' was blocked by capability isolation: {outcome.get('error')}",
                "needs_confirmation": outcome.get("category") == "isolation_ask",
            }
        )
    if outcome.get("category") == "unresolved":
        # "unresolved" means the capability registry doesn't recognize
        # this action at all (see ActionPipeline._fail's default
        # category) - not a pipeline crash, just an unregistered
        # capability. Fail-closed here too if it happens to be one of
        # the DESTRUCTIVE_TOOLS names (shouldn't normally happen, but
        # don't let a registration gap become a bypass either).
        from core.permissions import PermissionGate

        if tool_name in PermissionGate.DESTRUCTIVE_TOOLS:
            return json.dumps(
                {
                    "success": False,
                    "error": f"'{tool_name}' is a destructive action not found in the "
                    f"capability registry - denying by default rather than "
                    f"running it unprotected.",
                    "security_gate_unavailable": True,
                }
            )
        return execute_tool_call(tool_name, tool_dict)

    if not outcome.get("success"):
        return json.dumps({"success": False, "error": outcome.get("error") or "unknown error"})

    result = outcome.get("result")
    return result if isinstance(result, str) else json.dumps(result)


# multi_agent_swarm/ - see ai/multi_agent_swarm_tools.py's docstring for
# the gap (real package, never wired into schema or dispatch here).
from ai.multi_agent_swarm_tools import SWARM_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(SWARM_DIRECT_HANDLERS)

# Financial intelligence controls (expenses/budgets/market watchlist) -
# see ai/finance_tools.py.
from ai.finance_tools import FINANCE_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(FINANCE_DIRECT_HANDLERS)

# Wellness tracking controls (steps/water/sleep/workouts/mood/goals/
# streaks) - see ai/wellness_tools.py.
from ai.wellness_tools import WELLNESS_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(WELLNESS_DIRECT_HANDLERS)

# Cross-device pairing (start_pairing entry point + device list) - see
# ai/cross_device_tools.py and cross_device/runtime.py. Handler dict is
# populated regardless of the flag (cheap, stateless functions); the
# tool only ever appears in the schema, and therefore only ever gets
# called, when ULTRON_CROSS_DEVICE_ENABLED is on.
from ai.cross_device_tools import CROSS_DEVICE_DIRECT_HANDLERS  # noqa: E402

_DIRECT_HANDLERS.update(CROSS_DEVICE_DIRECT_HANDLERS)


_MAX_PARALLEL_WORKERS = 8


def run_tools_parallel(jobs):
    if not jobs:
        return []

    def _run_one(job):
        try:
            return job()
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    workers = min(len(jobs), _MAX_PARALLEL_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_run_one, jobs))
