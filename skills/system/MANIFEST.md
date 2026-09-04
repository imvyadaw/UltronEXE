# System skills

| Tool | Module |
|---|---|
| get_clipboard, set_clipboard | automation/clipboard/clipboard.py |
| type_text, press_key | automation/keyboard/keyboard.py |
| get_cpu_ram_usage, get_ip_address, get_system_info, get_battery_status | windows/system_info/status.py |
| lock_screen, shutdown_pc, restart_pc, sign_out, cancel_shutdown | windows/system_info/power.py |
| mouse_move, mouse_click, mouse_scroll | automation/mouse/mouse.py |
| start_macro_recording, stop_macro_recording, play_macro, list_macros | automation/macro/macro.py |
| save_workflow, run_workflow, list_workflows | automation/workflow/workflow.py |
| (find/click UI elements by name - module only, not an AI tool by default) | automation/ui/ui_automation.py |
| (background task scheduling - used internally by core/scheduler.py) | automation/scheduler/task_scheduler.py |
| remember_fact, recall_fact, search_facts, forget_fact | memory/long_term/long_term.py |
| remember_for_search, search_memory | memory/vector_db/vector_store.py |
| (persist/load full conversation sessions - module only) | memory/history/history.py |
| read_screen_text | vision/ocr/ocr.py (via vision/screen/capture.py) |
| detect_faces_on_screen | vision/face/face.py |
| detect_objects_on_screen | vision/object_detection/object_detection.py |
| find_ui_text_regions | vision/ui_detection/ui_detection.py |
| (hand landmark + gesture detection - module only, not an AI tool by default) | vision/gestures/gestures.py |
| (image brightness/color/edge stats - module only, not an AI tool by default) | vision/image_analysis/image_analysis.py |
| write_code, review_code, fix_code, explain_code | agents/coding_agent.py |
