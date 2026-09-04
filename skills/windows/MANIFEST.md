# Windows skills

Tool names the AI can call (see ai/prompts.py) and where they're implemented:

| Tool | Module |
|---|---|
| open_application, close_application, list_running_apps | windows/apps/manager.py |
| activate_window, click_ui_element, type_into_ui_element, list_ui_elements | automation/ui/ui_automation.py |
| set_volume, get_volume, mute, unmute | windows/audio/volume.py |
| media_play_pause, media_next, media_previous, media_volume_up/down, media_mute | windows/audio/media_keys.py |
| take_screenshot, sleep_display, get_brightness, set_brightness | windows/display/display.py |
| get_battery_status, get_system_info, get_cpu_ram_usage, get_ip_address | windows/system_info/status.py |
| lock_screen, shutdown_pc, restart_pc, sign_out, cancel_shutdown | windows/system_info/power.py |
| run_command | windows/cmd/runner.py |
| list_processes, find_process, kill_process, get_process_info | windows/process/process.py |
| (registry read/write - not exposed as a top-level AI tool; use RegistryTools directly) | windows/registry/registry.py |
| list_services, get_service_status, (start_service/stop_service - module only) | windows/services/services.py |
| list_startup_programs, (add/remove - module only) | windows/startup/startup.py |
| show_notification | windows/notifications/notifications.py |
| get_firewall_status, (rule list/add/remove - module only) | windows/firewall/firewall.py |
| get_defender_status, start_defender_scan | windows/defender/defender.py |
| open_explorer_at, reveal_file_in_explorer | windows/explorer/explorer.py |
| run_powershell | windows/powershell/powershell.py |

All modules above are implemented. A few methods (registry writes/deletes, firewall
rule management, service start/stop, startup add/remove) are real and callable
directly on the module or via `windows.get_system_tools()`, but are deliberately
not in the default AI tool schema (ai/tools_schema.py) to keep the tool-calling
list from growing too large - add them there + core/executor.py + groq_client.py's
tool_mapping if you want the AI to call them directly.
