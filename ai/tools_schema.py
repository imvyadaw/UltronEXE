"""
Tool schema
===========
Native Groq/OpenAI-style function-calling definitions for every real tool
Ultron exposes (see core/executor.py for the dispatch and skills/*/MANIFEST.md
for the tool -> module mapping). Passed as `tools=TOOLS` on every
chat.completions.create() call so the model returns structured tool_calls
instead of us having to regex-extract JSON out of its plain-text reply.

Keep this in sync with core/executor.py's tool_map and
ai/cloud_models/groq_client.py's _execute_tool_from_dict: every name here
must exist in both, and every parameter name here must match what those
two `d.get("...")` lookups expect.
"""


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
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


TOOLS = [
    # --- Internet -------------------------------------------------------
    _tool(
        "search_internet",
        "Search the web for up-to-date information not in your training data. "
        "Runs a silent background lookup and returns text results - this does NOT "
        "open a browser or any window. Use this (never open_application/open_url) "
        "to answer a factual/informational question, even if the user's message "
        "sounds like it needs a search.",
        {"query": {"type": "string", "description": "Search query"}},
        ["query"],
    ),
    _tool(
        "read_url",
        "Fetch and read the main text content of a specific web page.",
        {"url": {"type": "string", "description": "Full URL to read"}},
        ["url"],
    ),
    _tool(
        "fact_check_claim",
        "Check a specific claim/rumor against what published fact-checking "
        "organizations have rated it (not this model's own opinion). Use "
        "when the user asks to verify/confirm something, not for general "
        "look-ups (use search_internet for those).",
        {"claim": {"type": "string", "description": "The claim to check, as a short factual statement"}},
        ["claim"],
    ),
    _tool(
        "get_api_usage",
        "Report how many Groq API calls/tokens Ultron has used so far.",
    ),
    _tool(
        "get_weather",
        "Get current weather for a location.",
        {"location": {"type": "string", "description": "City name, or blank to auto-detect from IP"}},
    ),
    # --- Files & folders --------------------------------------------------
    _tool(
        "list_directory",
        "List the contents of a directory.",
        {"path": {"type": "string", "description": "Folder path, e.g. '~/Desktop'. Defaults to home."}},
    ),
    _tool(
        "find_folder",
        "Find a folder by name under a search path.",
        {
            "folder_name": {"type": "string"},
            "search_path": {"type": "string", "description": "Where to search. Defaults to home."},
        },
        ["folder_name"],
    ),
    _tool(
        "search_files",
        "Search for files matching a glob pattern (e.g. '*.pdf').",
        {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.pdf' or 'invoice*'"},
            "search_path": {"type": "string", "description": "Where to search. Defaults to home."},
        },
        ["pattern"],
    ),
    _tool(
        "read_file",
        "Read the text contents of a file.",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "get_file_info",
        "Get metadata about a file or folder (size, type, modified date).",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "open_file",
        "Open a file with its default Windows application.",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "create_folder",
        "Create a new folder, including any missing parent folders.",
        {"folder_path": {"type": "string"}},
        ["folder_path"],
    ),
    _tool(
        "create_file",
        "Create a new file with optional initial content.",
        {"file_path": {"type": "string"}, "content": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "write_file",
        "Overwrite or append text content to a file.",
        {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
            "append": {"type": "boolean", "description": "True to append instead of overwrite"},
        },
        ["file_path", "content"],
    ),
    _tool(
        "copy_file",
        "Copy a file or folder to a new location.",
        {"source": {"type": "string"}, "destination": {"type": "string"}},
        ["source", "destination"],
    ),
    _tool(
        "move_file",
        "Move or rename a file or folder.",
        {"source": {"type": "string"}, "destination": {"type": "string"}},
        ["source", "destination"],
    ),
    _tool(
        "delete_file",
        "Delete a file. Sends it to the Recycle Bin (not permanent).",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "delete_folder",
        "Delete a folder. Sends it to the Recycle Bin (not permanent).",
        {"folder_path": {"type": "string"}},
        ["folder_path"],
    ),
    # --- Applications -----------------------------------------------------
    _tool(
        "open_application",
        "Open/launch an application by name, visibly on the user's screen. If unsure "
        "whether the app exists, try anyway. Only call this when the user explicitly "
        "asked to open/launch that app - never as a way to look something up or "
        "answer a question (use search_internet for that instead).",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "close_application",
        "Close a running application by name.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool("list_running_apps", "List currently running applications with visible windows."),
    _tool(
        "activate_window",
        "Bring any open window to the foreground/focus by (partial) title match, so it's ready to receive clicks/typing. Works for any app, not just the browser.",
        {
            "window_title": {
                "type": "string",
                "description": "Full or partial window title, e.g. 'Notepad' or 'Untitled - Notepad'",
            }
        },
        ["window_title"],
    ),
    _tool(
        "click_ui_element",
        "Click a button, menu item, tab, or other UI element by its visible text/name inside any open application window - generic UI control for apps that aren't the browser (e.g. click 'Save' in Photoshop, click a menu item in Excel).",
        {
            "element_name": {
                "type": "string",
                "description": "Visible text/name of the element to click, e.g. 'Save', 'File', 'OK'",
            },
            "window_title": {
                "type": "string",
                "description": "Optional: restrict the search to a window whose title contains this text",
            },
        },
        ["element_name"],
    ),
    _tool(
        "type_into_ui_element",
        "Click a named text field/box inside any open application window, then type text into it - fills in forms/fields in apps that aren't the browser.",
        {
            "element_name": {"type": "string", "description": "Visible name of the text field/element to type into"},
            "text": {"type": "string", "description": "Text to type"},
            "window_title": {
                "type": "string",
                "description": "Optional: restrict the search to a window whose title contains this text",
            },
        },
        ["element_name", "text"],
    ),
    _tool(
        "list_ui_elements",
        "List clickable/visible UI elements (buttons, menu items, fields) inside a given open window - use this first to see what's available before clicking/typing into something.",
        {
            "window_title": {"type": "string", "description": "Window title (or part of it) to inspect"},
            "control_type": {"type": "string", "description": "Optional filter, e.g. 'Button', 'Edit', 'MenuItem'"},
        },
        ["window_title"],
    ),
    # --- Browser / Chrome ---------------------------------------------
    _tool(
        "open_url",
        "Open a single URL in the default browser, visibly on the user's screen. Only "
        "call this when the user explicitly asked to open/show a site or URL - never "
        "as a way to answer an informational question (use search_internet for that "
        "instead, which does not open a browser).",
        {"url": {"type": "string"}},
        ["url"],
    ),
    _tool(
        "open_urls",
        "Open multiple URLs, each in a new browser tab.",
        {"urls": {"type": "array", "items": {"type": "string"}}},
        ["urls"],
    ),
    _tool("list_chrome_tabs", "List all currently open tabs in Chrome."),
    _tool(
        "close_chrome_tab",
        "Close a single Chrome tab by matching its title.",
        {"tab": {"type": "string", "description": "Tab title or partial title match"}},
        ["tab"],
    ),
    _tool(
        "close_chrome_tabs",
        "Close multiple Chrome tabs by title match.",
        {"tabs": {"type": "array", "items": {"type": "string"}}},
        ["tabs"],
    ),
    _tool(
        "scroll_chrome",
        "Scroll the active Chrome tab.",
        {
            "direction": {"type": "string", "enum": ["up", "down", "left", "right", "top", "bottom"]},
            "amount": {"type": "integer", "description": "Pixels to scroll (ignored for top/bottom)"},
        },
    ),
    _tool(
        "chrome_navigate",
        "Navigate in Chrome: 'back', 'forward', 'refresh', or a URL.",
        {"action": {"type": "string"}},
        ["action"],
    ),
    _tool(
        "type_in_chrome",
        "Type text into the currently focused element in Chrome.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "chrome_keypress",
        "Press a single key in Chrome (enter, escape, tab, space, etc.).",
        {"key": {"type": "string"}},
    ),
    _tool(
        "chrome_zoom",
        "Zoom in, out, or reset zoom in Chrome.",
        {"action": {"type": "string", "enum": ["in", "out", "reset"]}},
    ),
    _tool(
        "youtube_search",
        "Open YouTube and search for a query (opens the results page only - "
        "does NOT start playback). Use youtube_play instead when the user "
        "wants something to actually start playing.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "youtube_play",
        "Search YouTube for a query and actually start playing the top "
        "result (e.g. 'play <song/video>', 'youtube pe <X> chalao'). Use "
        "this instead of youtube_search whenever the user wants playback "
        "to start, not just the search results shown.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "youtube_control",
        "Control YouTube playback (play/pause, skip, volume) via native shortcuts.",
        {"action": {"type": "string"}},
    ),
    # --- Audio / display / system -----------------------------------------
    _tool(
        "set_volume",
        "Set system volume.",
        {"level": {"type": "integer", "description": "0-100"}},
        ["level"],
    ),
    _tool("get_volume", "Get the current system volume."),
    _tool("mute", "Mute system audio."),
    _tool("unmute", "Unmute system audio."),
    _tool(
        "take_screenshot",
        "Take a screenshot and save it to the Desktop.",
        {"filename": {"type": "string", "description": "Optional custom filename"}},
    ),
    _tool("get_battery_status", "Get battery status (laptops only)."),
    _tool("get_cpu_ram_usage", "Get current CPU and RAM usage."),
    _tool(
        "get_disk_usage",
        "Get disk space usage (total/used/free) for a drive.",
        {"drive": {"type": "string", "description": "Drive letter, e.g. 'D:\\\\'. Omit for the home/system drive."}},
    ),
    _tool("get_system_info", "Get general system information (OS, hostname, etc.)."),
    _tool("get_ip_address", "Get the local IP address and hostname."),
    _tool("empty_trash", "Empty the Windows Recycle Bin."),
    _tool("sleep_display", "Turn off the monitor."),
    _tool("get_brightness", "Get current screen brightness."),
    _tool(
        "set_brightness",
        "Set screen brightness.",
        {"level": {"type": "integer", "description": "0-100"}},
        ["level"],
    ),
    _tool(
        "run_command",
        "Execute a command via cmd.exe. A short list of destructive commands is blocked.",
        {"command": {"type": "string"}},
        ["command"],
    ),
    # --- Power (all require explicit user confirmation first) -------------
    _tool("lock_screen", "Lock the Windows screen immediately."),
    _tool(
        "shutdown_pc",
        "Shut down the PC after a 30s grace period. ALWAYS ask the user "
        "'are you sure?' in plain text first; only pass confirm=true after "
        "they clearly say yes.",
        {"confirm": {"type": "boolean"}},
        ["confirm"],
    ),
    _tool(
        "restart_pc",
        "Restart the PC after a 30s grace period. ALWAYS ask the user "
        "'are you sure?' in plain text first; only pass confirm=true after "
        "they clearly say yes.",
        {"confirm": {"type": "boolean"}},
        ["confirm"],
    ),
    _tool(
        "sign_out",
        "Sign out of Windows immediately. ALWAYS ask the user 'are you "
        "sure?' in plain text first; only pass confirm=true after they "
        "clearly say yes.",
        {"confirm": {"type": "boolean"}},
        ["confirm"],
    ),
    _tool("cancel_shutdown", "Cancel a pending shutdown/restart."),
    # --- Media keys (work for any player, not just Chrome) -----------------
    _tool("media_play_pause", "Play/pause whatever media is currently active, system-wide."),
    _tool("media_next", "Skip to the next track, system-wide."),
    _tool("media_previous", "Go to the previous track, system-wide."),
    _tool("media_volume_up", "System volume up via media key."),
    _tool("media_volume_down", "System volume down via media key."),
    _tool("media_mute", "Toggle system mute via media key."),
    # --- Generic keyboard / clipboard / notes ------------------------------
    _tool(
        "type_text",
        "Type text into whatever window/field is currently focused.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "press_key",
        "Press a key or combo (e.g. 'enter', 'ctrl+s') in the focused window.",
        {"key": {"type": "string"}},
    ),
    _tool("get_clipboard", "Get the current clipboard text."),
    _tool(
        "set_clipboard",
        "Copy text to the clipboard.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "save_note",
        "Save a quick timestamped note.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool("read_notes", "Read back all saved notes."),
    # --- PDF / Office / Compression -----------------------------------------
    _tool(
        "extract_pdf_text",
        "Extract text content from a PDF file.",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "get_pdf_page_count",
        "Get the number of pages in a PDF.",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "merge_pdfs",
        "Merge multiple PDF files into one, in the given order.",
        {
            "file_paths": {"type": "array", "items": {"type": "string"}},
            "output_path": {"type": "string"},
        },
        ["file_paths", "output_path"],
    ),
    _tool(
        "create_pdf_from_text",
        "Create a simple PDF file from plain text.",
        {
            "file_path": {"type": "string"},
            "text": {"type": "string"},
            "title": {"type": "string"},
        },
        ["file_path", "text"],
    ),
    _tool(
        "read_docx",
        "Read the text content of a Word (.docx) document.",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "create_docx",
        "Create a Word (.docx) document from text content.",
        {
            "file_path": {"type": "string"},
            "content": {"type": "string", "description": "Body text, blank lines separate paragraphs"},
            "title": {"type": "string"},
        },
        ["file_path", "content"],
    ),
    _tool(
        "read_xlsx",
        "Read cell values from an Excel (.xlsx) file.",
        {
            "file_path": {"type": "string"},
            "sheet_name": {"type": "string", "description": "Defaults to the first sheet"},
        },
        ["file_path"],
    ),
    _tool(
        "create_xlsx",
        "Create an Excel (.xlsx) file from rows of data.",
        {
            "file_path": {"type": "string"},
            "rows": {
                "type": "array",
                "items": {"type": "array"},
                "description": "List of rows, each a list of cell values",
            },
        },
        ["file_path", "rows"],
    ),
    _tool(
        "compress_files",
        "Zip a file or folder into a .zip archive.",
        {
            "source_path": {"type": "string"},
            "output_path": {"type": "string", "description": "Defaults to source name + .zip"},
        },
        ["source_path"],
    ),
    _tool(
        "extract_archive",
        "Extract a .zip archive.",
        {
            "archive_path": {"type": "string"},
            "output_dir": {"type": "string", "description": "Defaults to a folder next to the archive"},
        },
        ["archive_path"],
    ),
    # --- Process management --------------------------------------------------
    _tool(
        "list_processes",
        "List running processes, sorted by memory or CPU usage.",
        {"sort_by": {"type": "string", "enum": ["memory", "cpu"]}, "limit": {"type": "integer"}},
    ),
    _tool(
        "find_process",
        "Find running process(es) matching a name.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "kill_process",
        "Kill a process by name or PID. Destructive - always ask the user before calling with confirm=true.",
        {
            "name": {"type": "string"},
            "pid": {"type": "integer"},
            "confirm": {"type": "boolean", "description": "Must be true to actually kill it"},
        },
    ),
    _tool(
        "get_process_info",
        "Get detailed info (CPU, memory, status) about a process by PID.",
        {"pid": {"type": "integer"}},
        ["pid"],
    ),
    # --- Windows services / startup / notifications / firewall / defender ---
    _tool(
        "list_services",
        "List Windows services and their status.",
        {"filter_status": {"type": "string", "enum": ["running", "stopped"]}},
    ),
    _tool(
        "get_service_status",
        "Get the status of a single Windows service by name.",
        {"service_name": {"type": "string"}},
        ["service_name"],
    ),
    _tool(
        "list_startup_programs",
        "List programs registered to launch automatically at Windows login.",
    ),
    _tool(
        "show_notification",
        "Show a native Windows toast notification.",
        {
            "title": {"type": "string"},
            "message": {"type": "string"},
            "duration": {"type": "integer"},
        },
        ["title", "message"],
    ),
    _tool("get_firewall_status", "Get Windows Firewall on/off status for all profiles."),
    _tool("get_defender_status", "Get Windows Defender's real-time protection status."),
    _tool("start_defender_scan", "Start a Windows Defender quick scan in the background."),
    _tool(
        "open_explorer_at",
        "Open File Explorer at a given folder path.",
        {"path": {"type": "string"}},
    ),
    _tool(
        "reveal_file_in_explorer",
        "Open File Explorer with a specific file selected/highlighted.",
        {"file_path": {"type": "string"}},
        ["file_path"],
    ),
    _tool(
        "run_powershell",
        "Run a PowerShell command and return its output. Blocks a short list of destructive commands.",
        {"script": {"type": "string"}},
        ["script"],
    ),
    # --- Edge / Firefox (parity with Chrome tools) ---------------------------
    _tool("list_edge_tabs", "List all open tabs in Microsoft Edge."),
    _tool(
        "close_edge_tab",
        "Close an Edge tab by matching its title.",
        {"tab": {"type": "string"}},
        ["tab"],
    ),
    _tool(
        "scroll_edge",
        "Scroll the active Edge tab.",
        {
            "direction": {"type": "string", "enum": ["up", "down", "left", "right", "top", "bottom"]},
            "amount": {"type": "integer"},
        },
    ),
    _tool(
        "edge_navigate",
        "Navigate in Edge: back, forward, refresh, or a URL.",
        {"action": {"type": "string"}},
        ["action"],
    ),
    _tool(
        "type_in_edge",
        "Type text into the currently focused element in Edge.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool("list_firefox_tabs", "List all open tabs in Firefox."),
    _tool(
        "close_firefox_tab",
        "Close a Firefox tab by matching its title.",
        {"tab": {"type": "string"}},
        ["tab"],
    ),
    _tool(
        "scroll_firefox",
        "Scroll the active Firefox tab.",
        {
            "direction": {"type": "string", "enum": ["up", "down", "left", "right", "top", "bottom"]},
            "amount": {"type": "integer"},
        },
    ),
    _tool(
        "firefox_navigate",
        "Navigate in Firefox: back, forward, refresh, or a URL.",
        {"action": {"type": "string"}},
        ["action"],
    ),
    _tool(
        "list_downloads",
        "List recently downloaded files.",
        {"limit": {"type": "integer"}},
    ),
    _tool(
        "open_download",
        "Open a file from the Downloads folder.",
        {"filename": {"type": "string"}},
        ["filename"],
    ),
    _tool(
        "get_download_history",
        "Get recent download history (filename + source URL) from Chrome or Edge.",
        {"browser": {"type": "string", "enum": ["chrome", "edge"]}, "limit": {"type": "integer"}},
    ),
    # --- Mouse / macros / workflows -------------------------------------------
    _tool(
        "mouse_move",
        "Move the mouse cursor to screen coordinates.",
        {"x": {"type": "integer"}, "y": {"type": "integer"}},
        ["x", "y"],
    ),
    _tool(
        "mouse_click",
        "Click the mouse at given coordinates, or the current position if omitted.",
        {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
        },
    ),
    _tool(
        "mouse_scroll",
        "Scroll the mouse wheel. Positive scrolls up, negative scrolls down.",
        {"amount": {"type": "integer"}},
        ["amount"],
    ),
    _tool("start_macro_recording", "Start recording mouse clicks and key presses as a macro."),
    _tool(
        "stop_macro_recording",
        "Stop recording and save the macro under a name.",
        {"macro_name": {"type": "string"}},
        ["macro_name"],
    ),
    _tool(
        "play_macro",
        "Replay a previously saved macro.",
        {"macro_name": {"type": "string"}, "speed": {"type": "number"}},
        ["macro_name"],
    ),
    _tool("list_macros", "List all saved macros."),
    _tool(
        "save_workflow",
        "Save a named sequence of tool calls as a reusable workflow.",
        {
            "workflow_name": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"tool": {"type": "string"}, "arguments": {"type": "object"}},
                },
            },
        },
        ["workflow_name", "steps"],
    ),
    _tool(
        "run_workflow",
        "Run a previously saved workflow, step by step.",
        {"workflow_name": {"type": "string"}},
        ["workflow_name"],
    ),
    _tool("list_workflows", "List all saved workflows."),
    # --- Memory: facts + similarity search -----------------------------------
    _tool(
        "remember_fact",
        "Store a durable structured fact about the user (e.g. a preference), keyed for later lookup.",
        {
            "key": {"type": "string"},
            "value": {"type": "string"},
            "category": {"type": "string", "description": "Groups related facts, e.g. 'preference', 'reminder'"},
        },
        ["key", "value"],
    ),
    _tool(
        "recall_fact",
        "Look up a previously stored fact by its key.",
        {"key": {"type": "string"}, "category": {"type": "string"}},
        ["key"],
    ),
    _tool(
        "search_facts",
        "Search stored facts whose key or value contains a query string.",
        {"query": {"type": "string"}, "category": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "forget_fact",
        "Delete a previously stored fact.",
        {"key": {"type": "string"}, "category": {"type": "string"}},
        ["key"],
    ),
    _tool(
        "remember_for_search",
        "Store a piece of text for later similarity/semantic search (as opposed to exact key lookup).",
        {"text": {"type": "string"}, "category": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "search_memory",
        "Find previously stored text most similar in meaning to a query.",
        {"query": {"type": "string"}, "top_k": {"type": "integer"}},
        ["query"],
    ),
    # --- Vision: OCR -----------------------------------------------------
    _tool(
        "read_screen_text",
        "Take a screenshot of the current screen and extract any visible text from it (OCR). "
        "Use this when the user asks what's on their screen, to read an error message, a chat "
        "window, or any other on-screen text you can't otherwise see.",
    ),
    _tool(
        "detect_faces_on_screen",
        "Detect how many faces (and where) are visible in the current screen - e.g. in an open "
        "video call or photo. Detection only - does not identify who anyone is.",
    ),
    _tool(
        "detect_objects_on_screen",
        "Detect common objects (person, car, dog, cat, bottle, chair, tv, etc - 20 categories) "
        "visible in the current screen.",
        {"confidence_threshold": {"type": "number", "description": "0-1, default 0.4"}},
    ),
    _tool(
        "find_ui_text_regions",
        "Find the on-screen locations of all visible text/labels (e.g. button captions, menu "
        "items), as a list of text + bounding box.",
    ),
    # --- Coding agent ------------------------------------------------------
    _tool(
        "write_code",
        "Write code from a natural-language specification. Use for substantial code-writing "
        "requests, as opposed to quick inline suggestions you can just answer directly.",
        {"spec": {"type": "string"}, "language": {"type": "string", "description": "e.g. python, javascript"}},
        ["spec"],
    ),
    _tool(
        "review_code",
        "Review a piece of code for bugs, edge cases, and style issues.",
        {"code": {"type": "string"}},
        ["code"],
    ),
    _tool(
        "fix_code",
        "Fix a bug in a piece of code, optionally given the error/traceback it produced.",
        {"code": {"type": "string"}, "error_message": {"type": "string"}},
        ["code"],
    ),
    _tool(
        "explain_code",
        "Explain what a piece of code does.",
        {"code": {"type": "string"}},
        ["code"],
    ),
    # --- Advanced workflows (core/workflow_engine.py) -----------------------
    _tool(
        "save_advanced_workflow",
        "Save a named multi-step workflow that supports passing a step's result into a "
        "later step's arguments via '{{stepN.output.some_field}}', and skipping a step "
        "unless an earlier step's result matches a condition. Each step is "
        "{tool, arguments, label?, run_if?, max_retries?}.",
        {
            "name": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}, "description": "List of step objects"},
        },
        ["name", "steps"],
    ),
    _tool(
        "run_advanced_workflow",
        "Run a previously saved advanced workflow by name.",
        {
            "name": {"type": "string"},
            "stop_on_error": {"type": "boolean", "description": "Default true"},
            "run_in_background": {"type": "boolean", "description": "Run without blocking; check status later"},
        },
        ["name"],
    ),
    _tool(
        "list_advanced_workflows",
        "List all saved advanced workflows.",
    ),
    # --- Background tasks (core/task_queue.py) ------------------------------
    _tool(
        "get_task_status",
        "Check the status of a previously submitted background task.",
        {"task_id": {"type": "string"}},
        ["task_id"],
    ),
    _tool(
        "list_background_tasks",
        "List recent background tasks and their status.",
        {"status": {"type": "string", "description": "Optional filter: pending, running, done, failed, cancelled"}},
    ),
    # --- Calendar (agents/calendar_agent.py) ---------------------------
    _tool(
        "add_calendar_event",
        "Add an event to the local calendar.",
        {
            "title": {"type": "string"},
            "start_time": {"type": "string", "description": "ISO-8601, e.g. 2026-08-05T14:00:00"},
            "end_time": {"type": "string", "description": "ISO-8601, optional"},
            "location": {"type": "string"},
            "notes": {"type": "string"},
        },
        ["title", "start_time"],
    ),
    _tool(
        "list_calendar_events",
        "List calendar events, optionally within an ISO-8601 time range.",
        {"start_time": {"type": "string"}, "end_time": {"type": "string"}},
    ),
    _tool(
        "upcoming_calendar_events",
        "List events starting within the next N hours.",
        {"within_hours": {"type": "integer", "description": "Default 24"}},
    ),
    _tool(
        "delete_calendar_event",
        "Delete a calendar event by id.",
        {"event_id": {"type": "string"}},
        ["event_id"],
    ),
    # --- To-do list (agents/task_agent.py) ------------------------------
    _tool(
        "add_todo",
        "Add an item to the persistent to-do list.",
        {
            "text": {"type": "string"},
            "priority": {"type": "string", "description": "low, normal, or high"},
            "due": {"type": "string", "description": "Optional ISO-8601 due date"},
        },
        ["text"],
    ),
    _tool("list_todos", "List to-do items.", {"include_done": {"type": "boolean"}}),
    _tool("complete_todo", "Mark a to-do item as done.", {"todo_id": {"type": "string"}}, ["todo_id"]),
    _tool("delete_todo", "Delete a to-do item.", {"todo_id": {"type": "string"}}, ["todo_id"]),
    # --- Health (agents/health_agent.py) --------------------------------
    _tool("log_water", "Log water intake in millilitres.", {"ml": {"type": "number"}}, ["ml"]),
    _tool(
        "log_sleep",
        "Log hours of sleep.",
        {"hours": {"type": "number"}, "note": {"type": "string"}},
        ["hours"],
    ),
    _tool(
        "log_exercise",
        "Log minutes of exercise/activity.",
        {"minutes": {"type": "number"}, "note": {"type": "string"}},
        ["minutes"],
    ),
    _tool("health_daily_summary", "Today's water/exercise/sleep totals."),
    # --- Security (agents/security_agent.py) ----------------------------
    _tool(
        "check_password_strength",
        "Score a password's strength (0-100) with reasons.",
        {"password": {"type": "string"}},
        ["password"],
    ),
    _tool(
        "generate_secure_password",
        "Generate a cryptographically random password.",
        {"length": {"type": "integer"}, "symbols": {"type": "boolean"}},
    ),
    _tool(
        "audit_file_permissions",
        "Check whether a file/folder is world-writable or unusually permissive.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    # --- Email (agents/email_agent.py) - requires EMAIL_ADDRESS/EMAIL_PASSWORD in .env
    _tool(
        "send_email",
        "Send a plain-text email via the configured SMTP account.",
        {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "cc": {"type": "string"},
        },
        ["to", "subject", "body"],
    ),
    _tool(
        "read_inbox",
        "List the most recent emails in the inbox.",
        {"limit": {"type": "integer"}, "unread_only": {"type": "boolean"}},
    ),
    _tool(
        "search_emails",
        "Search inbox subjects/senders for a query.",
        {"query": {"type": "string"}, "limit": {"type": "integer"}},
        ["query"],
    ),
    # --- Episodic / semantic / emotional memory --------------------------
    _tool(
        "record_event",
        "Log a timestamped event to episodic memory (what just happened).",
        {"event": {"type": "string"}, "context": {"type": "string"}, "tags": {"type": "string"}},
        ["event"],
    ),
    _tool("recall_recent_events", "List recent logged events.", {"limit": {"type": "integer"}}),
    _tool(
        "define_concept",
        "Store a general knowledge concept/definition in semantic memory.",
        {"concept": {"type": "string"}, "definition": {"type": "string"}},
        ["concept", "definition"],
    ),
    _tool("recall_concept", "Look up a stored concept's definition.", {"concept": {"type": "string"}}, ["concept"]),
    _tool(
        "log_mood",
        "Log an emotion label with a 1-5 intensity.",
        {"emotion": {"type": "string"}, "intensity": {"type": "integer"}, "note": {"type": "string"}},
        ["emotion"],
    ),
    _tool("get_mood_trend", "Average mood/valence trend over the last N days.", {"days": {"type": "integer"}}),
    # --- RAG + deep reasoning --------------------------------------------
    _tool(
        "rag_answer",
        "Answer a question grounded in Ultron's own stored memories/notes/facts, with sources.",
        {"question": {"type": "string"}, "top_k": {"type": "integer"}},
        ["question"],
    ),
    _tool(
        "reason_deeply",
        "Multi-step chain-of-thought: decompose a hard question into sub-questions, "
        "answer each, then synthesize a final answer. Slower than a normal reply - use "
        "for genuinely multi-part questions, not simple ones.",
        {"question": {"type": "string"}, "max_subquestions": {"type": "integer"}},
        ["question"],
    ),
    # --- Plugin marketplace ------------------------------------------------
    _tool("list_available_plugins", "List plugins available to install from the local catalog."),
    _tool(
        "install_plugin",
        "Scaffold a new plugin from the marketplace catalog under plugins/installed/.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    # --- App control (find/detect/launch/manage apps) ----------------------
    _tool("find_app", "Fuzzy-find an installed app by name.", {"query": {"type": "string"}}, ["query"]),
    _tool(
        "app_status",
        "Check whether an app is installed and/or currently running.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool(
        "restart_app",
        "Close an app (if running) and open it fresh again.",
        {"app_name": {"type": "string"}},
        ["app_name"],
    ),
    _tool("minimize_app", "Minimize all windows of an app.", {"app_name": {"type": "string"}}, ["app_name"]),
    _tool("maximize_app", "Maximize an app's window.", {"app_name": {"type": "string"}}, ["app_name"]),
    _tool("focus_app", "Bring an app's window to the foreground.", {"app_name": {"type": "string"}}, ["app_name"]),
    _tool(
        "close_all_by_category",
        "Close every running app in a category (browser, editor, media, communication, office, utility, development, creative).",
        {"category": {"type": "string"}},
        ["category"],
    ),
    _tool("kill_unresponsive_apps", "Force-close any window Windows has flagged as Not Responding."),
    _tool(
        "list_apps_by_category",
        "List installed apps belonging to a category.",
        {"category": {"type": "string"}},
        ["category"],
    ),
    # --- Window manager (geometry, snap, tile) ------------------------------
    _tool("list_windows", "List every open window with its title and geometry."),
    _tool(
        "get_window_geometry",
        "Get position/size/state of a window matching a title.",
        {"window_title": {"type": "string"}},
        ["window_title"],
    ),
    _tool(
        "move_window",
        "Move a window to x,y screen coordinates.",
        {"window_title": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"}},
        ["window_title", "x", "y"],
    ),
    _tool(
        "resize_window",
        "Resize a window to width x height.",
        {"window_title": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}},
        ["window_title", "width", "height"],
    ),
    _tool(
        "snap_window",
        "Snap a window to a screen zone.",
        {
            "window_title": {"type": "string"},
            "zone": {
                "type": "string",
                "enum": [
                    "left",
                    "right",
                    "top",
                    "bottom",
                    "top_left",
                    "top_right",
                    "bottom_left",
                    "bottom_right",
                    "full",
                ],
            },
        },
        ["window_title", "zone"],
    ),
    _tool(
        "minimize_window", "Minimize a window matching a title.", {"window_title": {"type": "string"}}, ["window_title"]
    ),
    _tool(
        "maximize_window", "Maximize a window matching a title.", {"window_title": {"type": "string"}}, ["window_title"]
    ),
    _tool(
        "restore_window",
        "Restore a minimized/maximized window to its normal size.",
        {"window_title": {"type": "string"}},
        ["window_title"],
    ),
    _tool("close_window", "Close a window matching a title.", {"window_title": {"type": "string"}}, ["window_title"]),
    _tool(
        "bring_window_to_front",
        "Focus a window, restoring it first if minimized.",
        {"window_title": {"type": "string"}},
        ["window_title"],
    ),
    _tool(
        "tile_windows",
        "Tile several windows side by side across the screen.",
        {"window_titles": {"type": "array", "items": {"type": "string"}}},
        ["window_titles"],
    ),
    # --- Virtual desktops ----------------------------------------------------
    _tool("list_virtual_desktops", "List all virtual desktops."),
    _tool("create_virtual_desktop", "Create a new virtual desktop."),
    _tool(
        "switch_virtual_desktop",
        "Switch to a virtual desktop by number.",
        {"desktop_number": {"type": "integer"}},
        ["desktop_number"],
    ),
    _tool("switch_next_virtual_desktop", "Switch to the next virtual desktop."),
    _tool("switch_previous_virtual_desktop", "Switch to the previous virtual desktop."),
    _tool("close_virtual_desktop", "Close the current virtual desktop."),
    _tool(
        "move_window_to_desktop",
        "Move a window to a specific virtual desktop.",
        {"window_title": {"type": "string"}, "desktop_number": {"type": "integer"}},
        ["window_title", "desktop_number"],
    ),
    # --- Power management (plans/sleep, distinct from shutdown/restart) ------
    _tool("sleep_now", "Put the PC to sleep immediately."),
    _tool("hibernate_now", "Hibernate the PC immediately."),
    _tool("list_power_plans", "List available Windows power plans."),
    _tool("get_active_power_plan", "Get the currently active Windows power plan."),
    _tool("set_power_plan", "Switch the active Windows power plan.", {"plan_name": {"type": "string"}}, ["plan_name"]),
    _tool(
        "set_sleep_timeout",
        "Set minutes of inactivity before sleep (0 = never).",
        {"minutes": {"type": "integer"}, "on_battery": {"type": "boolean"}},
        ["minutes"],
    ),
    _tool(
        "set_screen_timeout",
        "Set minutes of inactivity before the screen turns off (0 = never).",
        {"minutes": {"type": "integer"}, "on_battery": {"type": "boolean"}},
        ["minutes"],
    ),
    _tool("enable_battery_saver", "Switch to a battery-saving power plan."),
    _tool("disable_battery_saver", "Switch back to the balanced power plan."),
    # --- Accessibility ---------------------------------------------------------
    _tool("toggle_narrator", "Toggle Windows Narrator (screen reader) on/off."),
    _tool(
        "set_high_contrast", "Turn Windows High Contrast mode on or off.", {"enabled": {"type": "boolean"}}, ["enabled"]
    ),
    _tool("toggle_magnifier", "Toggle Windows Magnifier on/off."),
    _tool("set_sticky_keys", "Turn Sticky Keys on or off.", {"enabled": {"type": "boolean"}}, ["enabled"]),
    _tool("announce", "Speak text out loud immediately via TTS.", {"text": {"type": "string"}}, ["text"]),
    # --- Browser: bookmarks / history / tabs / forms ----------------------------
    _tool(
        "list_bookmarks",
        "List all bookmarks for a browser.",
        {"browser": {"type": "string", "enum": ["chrome", "edge"]}},
    ),
    _tool(
        "search_bookmarks",
        "Search bookmark names/URLs for a substring.",
        {"query": {"type": "string"}, "browser": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "add_bookmark",
        "Add a bookmark.",
        {
            "name": {"type": "string"},
            "url": {"type": "string"},
            "browser": {"type": "string"},
            "folder": {"type": "string"},
        },
        ["name", "url"],
    ),
    _tool(
        "delete_bookmark",
        "Delete a bookmark by exact name.",
        {"name": {"type": "string"}, "browser": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "recent_browser_history",
        "List most recently visited URLs.",
        {"browser": {"type": "string"}, "limit": {"type": "integer"}},
    ),
    _tool(
        "most_visited_sites",
        "List top sites by visit count.",
        {"browser": {"type": "string"}, "limit": {"type": "integer"}},
    ),
    _tool(
        "top_browsed_domains",
        "List top domains visited in the last N days.",
        {"browser": {"type": "string"}, "limit": {"type": "integer"}, "days": {"type": "integer"}},
    ),
    _tool(
        "browsing_activity_by_hour",
        "Visit counts bucketed by hour of day over the last N days.",
        {"browser": {"type": "string"}, "days": {"type": "integer"}},
    ),
    _tool(
        "search_browser_history",
        "Search browsing history titles/URLs.",
        {"query": {"type": "string"}, "browser": {"type": "string"}, "limit": {"type": "integer"}},
        ["query"],
    ),
    _tool("list_all_tabs", "List open tabs across Chrome, Edge, and Firefox."),
    _tool(
        "close_tab_in_browser",
        "Close a tab matching a title in a specific browser.",
        {"tab": {"type": "string"}, "browser": {"type": "string"}},
        ["tab"],
    ),
    _tool(
        "close_tabs_matching",
        "Close every open tab across all browsers whose title contains a query.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "fill_form_field",
        "Type a value into the currently focused form field.",
        {"value": {"type": "string"}, "press_tab_after": {"type": "boolean"}},
        ["value"],
    ),
    _tool(
        "fill_form_sequence",
        "Fill a sequence of form fields in order, tabbing between each.",
        {"values": {"type": "array", "items": {"type": "string"}}},
        ["values"],
    ),
    _tool("submit_form", "Press Enter to submit the currently focused form."),
    _tool(
        "save_form_profile",
        "Save a named autofill profile of field values.",
        {"profile_name": {"type": "string"}, "fields": {"type": "object"}},
        ["profile_name", "fields"],
    ),
    _tool(
        "autofill_form",
        "Fill the focused form using a saved autofill profile.",
        {"profile_name": {"type": "string"}, "field_order": {"type": "array", "items": {"type": "string"}}},
        ["profile_name", "field_order"],
    ),
    # --- RPA (record/play/edit step-based automation scripts) -------------------
    _tool("rpa_start_recording", "Start recording clicks/key presses as an RPA script."),
    _tool(
        "rpa_stop_recording",
        "Stop recording and save the RPA script under a name.",
        {"script_name": {"type": "string"}},
        ["script_name"],
    ),
    _tool(
        "rpa_play",
        "Replay a saved RPA script.",
        {"script_name": {"type": "string"}, "speed": {"type": "number"}, "loop": {"type": "integer"}},
        ["script_name"],
    ),
    _tool(
        "rpa_dry_run",
        "Validate an RPA script's steps without executing them.",
        {"script_name": {"type": "string"}},
        ["script_name"],
    ),
    _tool("rpa_list_scripts", "List saved RPA scripts."),
    _tool("rpa_delete_script", "Delete a saved RPA script.", {"script_name": {"type": "string"}}, ["script_name"]),
    # --- Fix (verification pass): these 3 had real handlers already wired
    # in core/executor.py's tool_map (rpa_recorder.add_step /
    # rpa_editor.insert_step / rpa_editor.delete_step) but were missing
    # here, so the model could never actually call them - schema is the
    # only thing the model sees, an unexposed handler is dead code from
    # its perspective. Adding them closes that gap with the real
    # signatures the executor already expects.
    _tool(
        "rpa_add_step",
        "Add a step to the RPA script currently being recorded.",
        {"step_type": {"type": "string", "description": "e.g. click, type, wait, key_press"}},
        ["step_type"],
    ),
    _tool(
        "rpa_insert_step",
        "Insert a step at a specific position in a saved RPA script.",
        {
            "script_name": {"type": "string"},
            "index": {"type": "integer"},
            "step": {"type": "object", "description": 'Step definition, e.g. {"type": "click", "x": 100, "y": 200}'},
        },
        ["script_name", "index", "step"],
    ),
    _tool(
        "rpa_delete_step",
        "Delete a specific step from a saved RPA script.",
        {"script_name": {"type": "string"}, "step_id": {"type": "string"}},
        ["script_name", "step_id"],
    ),
    # --- Triggers (fire a tool call on a file/time/system event) ----------------
    _tool(
        "watch_file",
        "Watch a file or folder; run a tool call when it changes.",
        {
            "path": {"type": "string"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "recursive": {"type": "boolean"},
        },
        ["path", "tool_name"],
    ),
    _tool("stop_watching_file", "Stop an active file watch.", {"watch_id": {"type": "string"}}, ["watch_id"]),
    _tool("list_file_watches", "List active file watches."),
    _tool(
        "add_daily_trigger",
        "Fire a tool call every day at a given time (optionally only on chosen weekdays).",
        {
            "hour": {"type": "integer"},
            "minute": {"type": "integer"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "days": {"type": "array", "items": {"type": "string"}},
            "label": {"type": "string"},
        },
        ["hour", "minute", "tool_name"],
    ),
    _tool(
        "add_interval_trigger",
        "Fire a tool call repeatedly every N seconds.",
        {
            "interval_seconds": {"type": "number"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "label": {"type": "string"},
        },
        ["interval_seconds", "tool_name"],
    ),
    _tool(
        "remove_time_trigger", "Remove a scheduled time trigger.", {"trigger_id": {"type": "string"}}, ["trigger_id"]
    ),
    _tool("list_time_triggers", "List scheduled time triggers."),
    _tool(
        "on_battery_threshold",
        "Fire a tool call once battery drops below a percent.",
        {
            "below_percent": {"type": "number"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "only_when_discharging": {"type": "boolean"},
            "label": {"type": "string"},
        },
        ["below_percent", "tool_name"],
    ),
    _tool(
        "on_process_start_trigger",
        "Fire a tool call when a process starts running.",
        {
            "process_name": {"type": "string"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "label": {"type": "string"},
        },
        ["process_name", "tool_name"],
    ),
    _tool(
        "on_process_stop_trigger",
        "Fire a tool call when a process stops running.",
        {
            "process_name": {"type": "string"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "label": {"type": "string"},
        },
        ["process_name", "tool_name"],
    ),
    _tool("list_system_triggers", "List active system-state triggers."),
    _tool(
        "remove_system_trigger", "Remove a system-state trigger.", {"trigger_id": {"type": "string"}}, ["trigger_id"]
    ),
    # --- Conditions & loops (branching/repetition over tool calls) --------------
    _tool(
        "evaluate_condition",
        "Evaluate a condition against live system state.",
        {"condition": {"type": "object"}},
        ["condition"],
    ),
    _tool(
        "run_if_condition",
        "Run one of two tool calls depending on whether a condition is true.",
        {"condition": {"type": "object"}, "then_step": {"type": "object"}, "else_step": {"type": "object"}},
        ["condition", "then_step"],
    ),
    _tool(
        "loop_repeat",
        "Run a tool call a fixed number of times.",
        {
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "times": {"type": "integer"},
            "delay_seconds": {"type": "number"},
        },
        ["tool_name", "times"],
    ),
    _tool(
        "loop_while",
        "Run a tool call repeatedly while a condition holds.",
        {
            "condition": {"type": "object"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "max_iterations": {"type": "integer"},
            "delay_seconds": {"type": "number"},
        },
        ["condition", "tool_name"],
    ),
    _tool(
        "loop_for_each",
        "Run a tool call once per item in a list.",
        {
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "items": {"type": "array"},
            "item_arg_name": {"type": "string"},
        },
        ["tool_name", "items", "item_arg_name"],
    ),
    # --- Vision Phase 4: scene understanding, form/diagram parsing, handwriting -
    # NOTE: named describe_screen_regions, NOT describe_screen - there's a
    # separate, question-answering describe_screen tool below (see
    # VISION_LLM_TOOLS). The two used to share the name "describe_screen"
    # by accident: core/executor.py's tool_map had two dict entries under
    # that one key, so the second (this one) silently shadowed the first
    # and the question-answering version could never actually run - fixed
    # as part of PHASE_29_C_CERTIFICATION's tool inventory audit. Keep
    # these two names distinct going forward.
    _tool(
        "describe_screen_regions",
        "Get a combined summary of what's currently on screen: visible text bucketed by "
        "screen region (top-left, center, etc), detected objects, and basic image stats "
        "(brightness, dominant colors). Use this for a general 'what am I looking at' question "
        "instead of calling OCR/object-detection separately.",
        {"include_objects": {"type": "boolean", "description": "Default true"}},
    ),
    _tool(
        "detect_form_fields",
        "Detect text-input boxes and checkboxes on the current screen, each paired with its "
        "best-guess nearby label. Heuristic (shape-based), may miss custom-styled fields.",
    ),
    _tool(
        "parse_diagram",
        "Parse a flowchart/diagram on the current screen into nodes (rectangle/diamond/ellipse "
        "shapes, each labeled from nearby text) and the lines connecting them. Works best on "
        "clean, high-contrast diagrams.",
    ),
    _tool(
        "read_handwriting",
        "Read handwritten text from an image file (or the current screen if no file_path given). "
        "Uses EasyOCR if installed (better for handwriting), else falls back to Tesseract.",
        {"file_path": {"type": "string", "description": "Optional path to an image file"}},
    ),
    # --- Voice Phase 4: user-programmable voice command shortcuts ---------------
    _tool(
        "add_voice_command",
        "Register a custom spoken phrase as a shortcut that directly triggers a tool call "
        "(e.g. running a saved workflow) without going through the LLM - e.g. phrase='good "
        "morning' -> tool_name='run_advanced_workflow', arguments={'name': 'morning_routine'}.",
        {
            "phrase": {"type": "string"},
            "tool_name": {"type": "string"},
            "arguments": {"type": "object"},
            "label": {"type": "string"},
        },
        ["phrase", "tool_name"],
    ),
    _tool(
        "remove_voice_command",
        "Remove a previously registered voice command shortcut.",
        {"phrase": {"type": "string"}},
        ["phrase"],
    ),
    _tool("list_voice_commands", "List all registered voice command shortcuts."),
    # --- Voice Phase 4: speaker recognition (records a short clip from the mic) -
    _tool(
        "enroll_speaker_voice",
        "Record a few seconds from the microphone and enroll it as a named speaker's voiceprint "
        "for later identification. Heuristic, not a secure biometric.",
        {"name": {"type": "string"}, "duration": {"type": "number", "description": "Seconds to record, default 4"}},
        ["name"],
    ),
    _tool(
        "identify_speaker_from_mic",
        "Record a few seconds from the microphone and identify which enrolled speaker it " "most resembles.",
        {"duration": {"type": "number", "description": "Seconds to record, default 4"}},
    ),
    _tool("list_enrolled_speakers", "List all enrolled speaker names."),
    _tool("forget_speaker", "Remove an enrolled speaker's voiceprint.", {"name": {"type": "string"}}, ["name"]),
    # --- Voice Phase 4: emotion detection ---------------------------------------
    _tool(
        "detect_voice_emotion",
        "Record a few seconds from the microphone and estimate the speaker's emotional tone "
        "(neutral/happy_excited/sad_calm/angry_stressed) from acoustic features. Heuristic, "
        "not a trained emotion-recognition model - treat as a rough hint.",
        {"duration": {"type": "number", "description": "Seconds to record, default 4"}},
    ),
    _tool(
        "analyze_text_sentiment",
        "Lightweight keyword-based sentiment check (positive/negative/neutral) on a piece of "
        "text - weaker signal than detect_voice_emotion but works on transcribed text with no mic.",
        {"text": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "set_tts_engine",
        "Switch the primary text-to-speech backend at runtime: 'edge' (neural voices, needs internet, "
        "default), 'gtts' (Google Translate TTS, needs internet, more languages incl. Hindi), or "
        "'pyttsx3' (fully offline OS-native voices, lower quality, always works with no internet).",
        {"engine": {"type": "string", "enum": ["edge", "gtts", "pyttsx3"]}},
        ["engine"],
    ),
    _tool(
        "list_voice_engines",
        "List the available TTS, STT, and wake word engines/modes for the voice stack, so the user can "
        "be told what's switchable (e.g. via set_tts_engine or the STT_MODE/WAKE_WORD_ENGINE .env settings).",
        {},
    ),
]

# --- New skills & integrations (skills/email, skills/calendar, skills/web,
# skills/data, skills/communication, integration/*) - see ai/new_skills_tools.py.
# Imported at the bottom (not the top) to avoid a circular import, since
# ai/new_skills_tools.py itself imports `_tool` from this module.
from ai.new_skills_tools import NEW_TOOLS  # noqa: E402

TOOLS = TOOLS + NEW_TOOLS

# --- Phase 27: movie assistant (modules/movie_assistant/) - see
# ai/movie_assistant_tools.py. Same bottom-import pattern as NEW_TOOLS
# above, for the same circular-import reason.
from ai.movie_assistant_tools import MOVIE_ASSISTANT_TOOLS  # noqa: E402

TOOLS = TOOLS + MOVIE_ASSISTANT_TOOLS

# --- Phase 6: app automations (apps/*) - see ai/apps_tools.py. Same
# bottom-import pattern as NEW_TOOLS above, for the same circular-import
# reason (ai/apps_tools.py imports `_tool` from this module).
from ai.apps_tools import APPS_TOOLS  # noqa: E402

TOOLS = TOOLS + APPS_TOOLS

# --- Phase 7: browser data (browser/chrome, edge, firefox downloads/
# cookies/bookmarks/history + automation/) - see ai/browser_tools.py.
# Same bottom-import pattern as above.
from ai.browser_tools import BROWSER_TOOLS  # noqa: E402

TOOLS = TOOLS + BROWSER_TOOLS

# --- Vision-LLM: understand/act on-screen content the accessibility tree
# (click_ui_element/list_ui_elements, pywinauto UIA) and classical CV
# (take_screenshot_and_read_text OCR) can't see - canvas-drawn web UI,
# images/charts, video frames, games, custom-rendered widgets. See
# vision/vision_llm.py. Prefer click_ui_element for normal Windows
# controls - it's faster and free; these are the fallback for anything
# visual that isn't an accessible control or clean text.
VISION_LLM_TOOLS = [
    _tool(
        "describe_screen",
        "Look at the current screen and answer a question about what's visible - "
        "e.g. 'what does this chart show', 'is there an error dialog open', "
        "'summarize this webpage'. Use this for anything visual a plain OCR/text "
        "read wouldn't capture.",
        {"question": {"type": "string", "description": "What to ask about the current screen."}},
        ["question"],
    ),
    _tool(
        "locate_on_screen",
        "Find something on screen by visual description (an icon, image, or "
        "canvas/web-rendered element with no accessible label) and return its "
        "approximate pixel coordinates, without clicking it. Prefer "
        "list_ui_elements/click_ui_element first for normal Windows controls - "
        "use this only when those don't find the target.",
        {"target": {"type": "string", "description": "Plain-English description of what to find."}},
        ["target"],
    ),
    _tool(
        "click_by_vision",
        "Locate something on screen by visual description and click it - a "
        "vision-based fallback for icons, images, or canvas/web-rendered "
        "elements with no accessible label. Prefer click_ui_element first for "
        "normal Windows controls; use this only when that fails or the target "
        "isn't a labeled control.",
        {
            "target": {"type": "string", "description": "Plain-English description of what to click."},
            "double_click": {"type": "boolean", "description": "Double-click instead of single-click. Default false."},
        },
        ["target"],
    ),
]

TOOLS = TOOLS + VISION_LLM_TOOLS

# --- Visual automator: vision-grounded desktop click/type (fallback for
# non-accessible UI) - see ai/visual_automator_tools.py.
from ai.visual_automator_tools import VISUAL_AUTOMATOR_TOOLS  # noqa: E402

TOOLS = TOOLS + VISUAL_AUTOMATOR_TOOLS

# --- Phase 18.9.2 self-management (health/auto-fix log, morning/evening
# briefs, health reminders, meeting prep, travel alerts) and Phase 18.6 AI
# agent personas (analyst/researcher/teacher/writer/guard) - see
# core/executor.py's tool_map for the dispatch, docs/TASK6_DORMANT_AUDIT.md
# for what these are and why they were previously disconnected.
PHASE18_TOOLS = [
    _tool(
        "report_component_health",
        'Record a status ("ok"/"warn"/"fail") for a named component of '
        "this assistant or the system, so get_overall_health can roll it up "
        "later. This only logs a report - it never checks anything itself.",
        {
            "component": {"type": "string", "description": "Name of the component being reported on."},
            "status": {"type": "string", "enum": ["ok", "warn", "fail"]},
            "detail": {"type": "string", "description": "Optional free-text detail."},
        },
        ["component", "status"],
    ),
    _tool(
        "get_overall_health",
        "Get the current overall health verdict (ok/warn/fail/unknown), "
        "rolled up from every component's most recent report_component_health call.",
    ),
    _tool(
        "suggest_fix_for_component",
        "List any previously-registered candidate fixes for a named "
        "component. Never invents a fix - only returns what's registered.",
        {"component": {"type": "string"}},
        ["component"],
    ),
    _tool(
        "suggest_fixes_for_failing",
        "List candidate fixes for every component currently reporting " '"fail" status.',
    ),
    _tool(
        "log_restart",
        "Log that a component was restarted and why. Bookkeeping only - " "does not actually restart anything.",
        {
            "component": {"type": "string"},
            "reason": {"type": "string"},
        },
        ["component"],
    ),
    _tool(
        "get_current_version",
        "Get the most recently recorded version string for this assistant, if any.",
    ),
    _tool(
        "add_morning_brief_item",
        "File one line of text under a section of today's (or a given "
        'date\'s) morning brief, e.g. section="calendar" text="9am standup". '
        "Does not decide what belongs in the brief - the caller supplies that.",
        {
            "section": {"type": "string", "description": 'e.g. "calendar", "tasks", "weather".'},
            "text": {"type": "string"},
            "priority": {"type": "integer", "description": "Higher surfaces first within the section. Default 0."},
            "for_date": {"type": "string", "description": "ISO YYYY-MM-DD. Defaults to today."},
        },
        ["section", "text"],
    ),
    _tool(
        "get_morning_brief",
        "Get everything filed for today's (or a given date's) morning " "brief, grouped by section.",
        {"for_date": {"type": "string", "description": "ISO YYYY-MM-DD. Defaults to today."}},
    ),
    _tool(
        "log_evening_event",
        "File one note/event under today's (or a given date's) evening " "wrap-up.",
        {
            "text": {"type": "string"},
            "kind": {"type": "string", "description": 'e.g. "note", "done", "pending". Default "note".'},
            "for_date": {"type": "string"},
        },
        ["text"],
    ),
    _tool(
        "get_evening_wrap",
        "Get today's (or a given date's) filed evening wrap-up events.",
        {"for_date": {"type": "string"}},
    ),
    _tool(
        "register_health_reminder",
        'Register a recurring wellness reminder (e.g. "stand up", '
        '"drink water") that repeats every interval_hours until acknowledged.',
        {
            "reminder_id": {"type": "string"},
            "label": {"type": "string"},
            "interval_hours": {"type": "number"},
        },
        ["reminder_id", "label", "interval_hours"],
    ),
    _tool(
        "get_due_health_reminders",
        "List wellness reminders that are currently due (registered via "
        "register_health_reminder and not yet acknowledged this interval).",
    ),
    _tool(
        "acknowledge_health_reminder",
        "Mark a wellness reminder as acknowledged, resetting its interval.",
        {"reminder_id": {"type": "string"}},
        ["reminder_id"],
    ),
    _tool(
        "register_meeting_prep",
        "Register an upcoming meeting so prep notes can be filed against it.",
        {
            "meeting_id": {"type": "string"},
            "title": {"type": "string"},
            "start_time": {"type": "number", "description": "Unix timestamp."},
            "attendees": {"type": "array", "items": {"type": "string"}},
        },
        ["meeting_id", "title", "start_time"],
    ),
    _tool(
        "add_meeting_prep_note",
        "File one prep note against a registered meeting.",
        {"meeting_id": {"type": "string"}, "note": {"type": "string"}},
        ["meeting_id", "note"],
    ),
    _tool(
        "get_upcoming_meetings_with_prep",
        "List registered meetings starting within the next N hours, with any filed prep notes.",
        {"within_hours": {"type": "number", "description": "Default 24."}},
    ),
    _tool(
        "register_trip",
        "Register an upcoming trip so get_travel_alerts can warn about it " "approaching.",
        {
            "trip_id": {"type": "string"},
            "destination": {"type": "string"},
            "depart_time": {"type": "number", "description": "Unix timestamp."},
            "mode": {"type": "string", "description": 'e.g. "flight", "train". Optional.'},
        },
        ["trip_id", "destination", "depart_time"],
    ),
    _tool(
        "get_travel_alerts",
        "List registered trips departing within the next N hours that haven't been alerted yet.",
        {"within_hours": {"type": "number", "description": "Default 24."}},
    ),
    _tool(
        "analyze_text_with_data_lens",
        "Have the analyst persona read a block of text and answer a "
        "specific analytical question about it (patterns, summary stats "
        "implied by the text, etc.) - distinct from general chat, tuned "
        "for data-oriented framing.",
        {
            "text": {"type": "string"},
            "question": {"type": "string", "description": "Optional specific question to answer about the text."},
        },
        ["text"],
    ),
    _tool(
        "analyze_numbers",
        "Compute exact descriptive statistics (mean/median/min/max/trend) "
        "over a list of numbers, with an optional plain-language "
        "interpretation of the already-computed stats. The stats "
        "themselves are exact arithmetic, never LLM-estimated.",
        {
            "data": {"type": "array", "items": {"type": "number"}},
            "interpret": {"type": "boolean", "description": "Add a plain-language interpretation. Default true."},
        },
        ["data"],
    ),
    _tool(
        "research_topic",
        "Research a topic by actually searching the web for sources and "
        "summarizing only what those sources say (grounded, not from "
        "training data) - more thorough than a single search_internet call.",
        {
            "topic": {"type": "string"},
            "num_sources": {"type": "integer", "description": "Default 5."},
        },
        ["topic"],
    ),
    _tool(
        "verify_claim_with_sources",
        "Verify a specific claim against published fact-checking sources, "
        "with attribution to what each source rated it - use "
        "fact_check_claim for a quicker single-source check, this for a "
        "more thorough multi-source one.",
        {"claim": {"type": "string"}},
        ["claim"],
    ),
    _tool(
        "explain_topic_for_learning",
        "Have the teacher persona explain a topic from scratch at a given "
        "level, broken into steps rather than dense prose.",
        {
            "topic": {"type": "string"},
            "level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
        },
        ["topic"],
    ),
    _tool(
        "quiz_me_on_topic",
        "Generate a short quiz (a few questions) on a topic, for the user to test their own understanding.",
        {
            "topic": {"type": "string"},
            "num_questions": {"type": "integer", "description": "Default 3."},
        },
        ["topic"],
    ),
    _tool(
        "draft_text",
        "Have the writer persona draft a piece of text (message, post, "
        "email body, etc.) for a given task, tone, and length. Text-only - "
        "does not send or post it anywhere; pair with the relevant send "
        "tool for that.",
        {
            "task": {"type": "string", "description": 'What to write, e.g. "a follow-up email after a job interview".'},
            "tone": {"type": "string", "description": 'e.g. "neutral", "formal", "casual". Default neutral.'},
            "length": {"type": "string", "enum": ["short", "medium", "long"]},
        },
        ["task"],
    ),
    _tool(
        "rewrite_text",
        "Have the writer persona rewrite existing text per an instruction " "(shorter, more formal, friendlier, etc.).",
        {"text": {"type": "string"}, "instruction": {"type": "string"}},
        ["text", "instruction"],
    ),
    _tool(
        "guard_review_content",
        "Rule-based (not LLM-based) safety review of a piece of code or "
        "text before acting on or sending it - flags things like obvious "
        "secrets, destructive commands, or unsafe patterns. Deliberately "
        "not the same model judging its own output.",
        {
            "content": {"type": "string"},
            "kind": {"type": "string", "enum": ["code", "text"]},
        },
        ["content"],
    ),
    _tool(
        "call_phone",
        "Place a phone call by handing the number off to the OS's "
        "registered tel: handler (e.g. Phone Link on Windows 11 with a "
        "paired Android phone) - does not guarantee the call connects, "
        "only that the handoff happened. Give either `number` directly, "
        "or a saved contact's `name` (looked up via find_contact - fails "
        "with a clear error rather than guessing if the name is unknown "
        "or ambiguous). Safety-gated: first call without confirm=true to "
        "check the number/name resolves, then call again with "
        "confirm=true only after the user has confirmed they want the "
        "call placed.",
        {
            "number": {
                "type": "string",
                "description": 'Phone number to call, e.g. "+91XXXXXXXXXX". Omit if using `name` instead.',
            },
            "name": {
                "type": "string",
                "description": 'Saved contact name to call instead of a raw number, e.g. "Mummy".',
            },
            "confirm": {"type": "boolean", "description": "Must be true to actually place the call."},
        },
    ),
    # --- Contacts (agents/contacts_agent.py) -----------------------------
    _tool(
        "add_contact",
        "Save a contact's name, phone number, and/or email to the local "
        "contacts store, so call_phone and similar tools can be given a "
        "name instead of a raw number.",
        {
            "name": {"type": "string", "description": 'Contact\'s name, e.g. "Mummy".'},
            "phone": {"type": "string", "description": 'Phone number, e.g. "+91XXXXXXXXXX".'},
            "email": {"type": "string", "description": "Email address."},
            "notes": {"type": "string", "description": "Any freeform note about this contact."},
        },
        ["name"],
    ),
    _tool(
        "find_contact",
        "Look up a saved contact by name (exact match first, then a "
        "substring match if exactly one contact matches). Returns an "
        "error if the name matches several contacts, rather than "
        "guessing which one was meant.",
        {"name": {"type": "string", "description": "Full or partial contact name to search for."}},
        ["name"],
    ),
    _tool(
        "list_contacts",
        "List every saved contact (name, phone, email, notes).",
    ),
    _tool(
        "delete_contact",
        "Remove a saved contact by exact name.",
        {"name": {"type": "string", "description": "Exact contact name to remove."}},
        ["name"],
    ),
    # --- Google Calendar (PHASE_18_7_AUTOMATION/CONNECT/calendar.py) ----
    # Distinct from add_calendar_event/list_calendar_events above, which
    # are a local offline SQLite calendar - these two sync with the
    # user's real Google account instead. Needs GOOGLE_CALENDAR_ACCESS_TOKEN
    # configured in .env; returns an empty list / {"success": False} with
    # a clear error otherwise, same failure-safe contract as every other
    # CONNECT/*.py module.
    _tool(
        "google_calendar_list_events",
        "List upcoming events from the user's real Google Calendar "
        "(cloud-synced, not the local offline calendar). Requires "
        "GOOGLE_CALENDAR_ACCESS_TOKEN to be configured.",
        {"num": {"type": "integer", "description": "Max number of upcoming events to return (default 5)."}},
    ),
    _tool(
        "google_calendar_create_event",
        "Create an event directly on the user's real Google Calendar "
        "(cloud-synced, not the local offline calendar). Requires "
        "GOOGLE_CALENDAR_ACCESS_TOKEN to be configured.",
        {
            "summary": {"type": "string", "description": "Event title."},
            "start_iso": {
                "type": "string",
                "description": 'Start time, full ISO 8601 with timezone, e.g. "2026-08-20T15:00:00+05:30".',
            },
            "end_iso": {"type": "string", "description": "End time, same ISO 8601 format."},
            "description": {"type": "string", "description": "Optional event description."},
        },
        ["summary", "start_iso", "end_iso"],
    ),
    # --- Social (PHASE_18_7_AUTOMATION/CONNECT/social.py) ----------------
    _tool(
        "post_to_social",
        "Post a short text message to pre-configured webhook targets "
        "(e.g. Slack, Discord, or a Zapier/IFTTT relay fanning out to "
        "Twitter/Instagram) - not native OAuth posting to any platform "
        "directly. Each target is one SOCIAL_WEBHOOK_<NAME> environment "
        "variable; with none configured this returns an error rather "
        "than silently doing nothing.",
        {
            "message": {"type": "string", "description": "Text to post."},
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": 'Optional - only post to these targets by name (e.g. ["discord"]). Omit to post to all configured targets.',
            },
        },
        ["message"],
    ),
]
TOOLS = TOOLS + PHASE18_TOOLS

# Verification-pass fix: skills/utilities/tools.py had 19 real, working
# actions with no schema entry - model could never call them. See
# ai/utility_tools_wire.py for the fix and why. Same bottom-import
# pattern as NEW_TOOLS above, for the same circular-import reason.
from ai.utility_tools_wire import UTILITY_TOOLS  # noqa: E402

TOOLS = TOOLS + UTILITY_TOOLS

# Verification-pass fix: agents/vision_agent.py's enroll_face/recognize_faces/
# find_icon_buttons/start_recording/stop_recording had no schema entry at
# all - the model didn't know these existed. See ai/vision_agent_tools.py.
from ai.vision_agent_tools import VISION_AGENT_TOOLS  # noqa: E402

TOOLS = TOOLS + VISION_AGENT_TOOLS

# Verification-pass fix: get_admin_status/relaunch_as_admin - see
# ai/admin_tools.py and windows/system_info/admin.py for why these are
# new (no elevation check existed anywhere before this).
from ai.admin_tools import ADMIN_TOOLS  # noqa: E402

TOOLS = TOOLS + ADMIN_TOOLS

# Deep-audit fix: ai/phase30_new_tools.py (currency_convert, translate_text,
# get_word_definition), ai/phase30_advanced_tools.py (find_and_process_files,
# find_duplicates, get_folder_stats, unified_search, get_desktop_state,
# save_contact, get_contact), and ai/image_display_tools.py (show_image) were
# all fully implemented and working but never referenced here, so the model
# never saw them and could never call them. Same bottom-import pattern as
# every registry above.
from ai.phase30_new_tools import PHASE30_TOOLS  # noqa: E402
from ai.phase30_advanced_tools import PHASE30_ADVANCED_TOOLS  # noqa: E402
from ai.image_display_tools import IMAGE_DISPLAY_TOOLS  # noqa: E402

TOOLS = TOOLS + PHASE30_TOOLS + PHASE30_ADVANCED_TOOLS + IMAGE_DISPLAY_TOOLS

# Deep-audit fix, item #4 (safe batch): reasoning/, advanced_memory/,
# quantum_dashboard/, command/, display/, mouth/, skill_creator/ - 7 more
# fully-implemented packages that were never imported anywhere. See
# ai/phase30_extended_tools.py's module docstring for why these are the
# safe-to-expose half; the real-world-reach half is in
# ai/phase30_gated_tools.py, gated off by default.
from ai.phase30_extended_tools import PHASE30_EXTENDED_TOOLS  # noqa: E402

TOOLS = TOOLS + PHASE30_EXTENDED_TOOLS

# Deep-audit fix, item #4 (gated batch): devices/, autonomous_web/ - real-
# world-reach capabilities, off by default. See
# ai/phase30_gated_tools.py's module docstring. Schema entries only appear
# once ULTRON_DEVICES_ENABLED / ULTRON_AUTONOMOUS_WEB_ENABLED are set.
from ai.phase30_gated_tools import PHASE30_GATED_TOOLS  # noqa: E402

TOOLS = TOOLS + PHASE30_GATED_TOOLS

# P1: Mission Persistence Engine + Tool-Chain Optimizer + Capability
# Isolation (ai/p1_engine_tools.py, see file docstring for the backing
# implementations). Same append-at-the-end pattern as every other
# batch above.
from ai.p1_engine_tools import P1_ENGINE_TOOLS  # noqa: E402

TOOLS = TOOLS + P1_ENGINE_TOOLS

# P2: Evidence Ledger & Confidence Tracking + Failure Pattern Learning
# Engine (ai/p2_engine_tools.py, see file docstring for the backing
# implementations).
from ai.p2_engine_tools import P2_ENGINE_TOOLS  # noqa: E402

TOOLS = TOOLS + P2_ENGINE_TOOLS

# P3: Unified Personal Knowledge OS + Resource-Aware Intelligence Engine
# (ai/p3_engine_tools.py, see file docstring for the backing
# implementations).
from ai.p3_engine_tools import P3_ENGINE_TOOLS  # noqa: E402

TOOLS = TOOLS + P3_ENGINE_TOOLS

# P4: Automatic Tool Benchmarking & Reliability Scoring + Conflict
# Resolution Engine (ai/p4_engine_tools.py, see file docstring for the
# backing implementations).
from ai.p4_engine_tools import P4_ENGINE_TOOLS  # noqa: E402

TOOLS = TOOLS + P4_ENGINE_TOOLS

# P5: Personal Workflow Graph & Automation Discovery
# (ai/p5_engine_tools.py, see file docstring for the backing
# implementation).
from ai.p5_engine_tools import P5_ENGINE_TOOLS  # noqa: E402

TOOLS = TOOLS + P5_ENGINE_TOOLS

# Camera+vision skill (skills/vision/) - physical webcam capture+describe,
# distinct from the screen-based Vision:OCR tools above. See
# ai/vision_skill_tools.py for why these 3 specifically.
from ai.vision_skill_tools import VISION_SKILL_TOOLS  # noqa: E402

TOOLS = TOOLS + VISION_SKILL_TOOLS

# Change-detection skill (skills/vision/change_detector.py) - "has the
# camera's view changed since a baseline", distinct from camera_see/
# camera_analyze_scene above. See ai/change_detection_tools.py.
from ai.change_detection_tools import CHANGE_DETECTION_TOOLS  # noqa: E402

TOOLS = TOOLS + CHANGE_DETECTION_TOOLS


# --- De-duplicate by function name -----------------------------------------
# TOOLS is a plain concatenation of several registries (base + NEW_TOOLS +
# APPS_TOOLS + BROWSER_TOOLS), and at least one name - spotify_next_track/
# spotify_previous_track - is registered in BOTH ai/new_skills_tools.py and
# ai/apps_tools.py. Sending two function specs with the identical name in
# one API call is invalid for most tool-calling APIs (Groq included) and
# was silently producing duplicate entries here. ai/tool_runtime.py's own
# _DIRECT_HANDLERS.update() chain already resolves such collisions in favor
# of the LAST registry applied (apps_tools.py wins over new_skills_tools.py,
# browser_tools.py wins over apps_tools.py) - keep-last below matches that
# so the schema sent to the model always agrees with which handler actually
# runs.
def _dedupe_tools_keep_last(tools: list) -> list:
    by_name = {}
    for spec in tools:
        by_name[spec["function"]["name"]] = spec
    return list(by_name.values())


# --- system_control/system_config/*: registry manager+backup, env vars,
# system properties, device manager control, Windows Update - see
# ai/system_config_tools.py. Same bottom-import pattern as NEW_TOOLS
# above, for the same circular-import reason.
from ai.system_config_tools import SYSTEM_CONFIG_TOOLS  # noqa: E402

TOOLS = TOOLS + SYSTEM_CONFIG_TOOLS

# --- system_control/process/*: startup manager, background/running
# processes, native Windows Task Scheduler - see ai/process_control_tools.py.
# Same bottom-import pattern as above, for the same circular-import reason.
from ai.process_control_tools import PROCESS_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + PROCESS_CONTROL_TOOLS

# --- system_control/files/*: encryption, permissions, network sharing,
# sync, backup/recovery - see ai/file_control_tools.py. Same
# bottom-import pattern as above, for the same circular-import reason.
from ai.file_control_tools import FILE_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + FILE_CONTROL_TOOLS

# --- system_control/network/*: Wi-Fi, Ethernet, VPN control - see
# ai/network_control_tools.py. Same bottom-import pattern as above, for
# the same circular-import reason.
from ai.network_control_tools import NETWORK_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + NETWORK_CONTROL_TOOLS

# --- system_control/security/*: Defender, all-registered-AV status,
# ransomware/Controlled-Folder-Access, BitLocker, local user accounts,
# password/lockout policy - see ai/security_control_tools.py. Same
# bottom-import pattern as above, for the same circular-import reason.
from ai.security_control_tools import SECURITY_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + SECURITY_CONTROL_TOOLS

# --- system_control/ui/*: theme/dark-mode, accent color, taskbar,
# Start menu, mouse cursor, lock screen, notifications/Focus Assist,
# Widgets board - see ai/ui_control_tools.py. Same bottom-import
# pattern as above, for the same circular-import reason.
from ai.ui_control_tools import UI_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + UI_CONTROL_TOOLS

# --- system_control/automation/*: saved PowerShell/batch script
# libraries, native (USB/display/power-source/event-log) triggers,
# native job pipelines, system macros, and recurring backup jobs -
# see ai/automation_control_tools.py. Same bottom-import pattern as
# above, for the same circular-import reason.
from ai.automation_control_tools import AUTOMATION_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + AUTOMATION_CONTROL_TOOLS

# --- system_control/storage/*: disk/partition management, volume
# formatting and filesystem control - see ai/storage_control_tools.py.
# Same bottom-import pattern as above, for the same circular-import
# reason.
from ai.storage_control_tools import STORAGE_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + STORAGE_CONTROL_TOOLS

# --- system_control/applications/*: installed-application lifecycle
# (package discovery/install, uninstall, updates, per-app compatibility
# settings, appdata backup, cache cleanup) - see
# ai/application_control_tools.py. Same bottom-import pattern as
# above, for the same circular-import reason.
from ai.application_control_tools import APPLICATION_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + APPLICATION_CONTROL_TOOLS

# --- system_control/monitoring/*: deep Windows OS instrumentation -
# temperature, event log, reliability index, per-process resource I/O,
# adapter link health, disk health, battery wear, startup/boot impact,
# OS-recorded crash history, and the combined performance report - see
# ai/monitoring_control_tools.py. Same bottom-import pattern as above,
# for the same circular-import reason.
from ai.monitoring_control_tools import MONITORING_CONTROL_TOOLS  # noqa: E402
from ai.hardware_extra_control_tools import HARDWARE_EXTRA_TOOLS  # noqa: E402

TOOLS = TOOLS + MONITORING_CONTROL_TOOLS
TOOLS = TOOLS + HARDWARE_EXTRA_TOOLS

# --- system_control/special/*: face recognition device control,
# gesture-to-action bindings, predictive-action approval, unified
# context snapshot + rules, self-optimization passes, emergency/panic
# mode, habit-to-automation bridge, multi-user profile linking, and
# scoped remote-access grants - see ai/special_control_tools.py. Same
# bottom-import pattern as above, for the same circular-import reason.
from ai.special_control_tools import SPECIAL_CONTROL_TOOLS  # noqa: E402

TOOLS = TOOLS + SPECIAL_CONTROL_TOOLS

# intelligence/decision_engine.py, goal_planner.py, intent_analyzer.py,
# reasoning_engine.py, self_critique.py, verification_engine.py,
# model_trainer.py - was never imported anywhere before this. See
# ai/cognitive_tools.py.
from ai.cognitive_tools import COGNITIVE_TOOLS  # noqa: E402

TOOLS = TOOLS + COGNITIVE_TOOLS

# agents/coder.py (CoderAgent) - was never imported anywhere before this.
# See ai/agent_tools.py's docstring for why only coder.py is wired here.
from ai.agent_tools import AGENT_TOOLS  # noqa: E402

TOOLS = TOOLS + AGENT_TOOLS

# skills/skill_executor.py's BaseSkill dispatch path - the one real
# accidental gap found in the audit (17 skills unreachable from live
# commands). See ai/skill_executor_tools.py.
from ai.skill_executor_tools import SKILL_EXECUTOR_TOOLS  # noqa: E402

TOOLS = TOOLS + SKILL_EXECUTOR_TOOLS

# networking/ (http/ssh/ftp/websocket clients), perception/ (on-demand
# activity/emotion/screen/system snapshots), scenarios/ (morning/evening
# briefings, meeting + work-break check-ins), and scheduler/ (schedule a
# tool call for later/recurring) - four dormant packages found with zero
# references anywhere else in the codebase, see each ai/*_tools.py
# module's own docstring for the audit. Same bottom-import pattern as
# above, for the same circular-import reason.
from ai.networking_tools import NETWORKING_TOOLS  # noqa: E402
from ai.perception_tools import PERCEPTION_TOOLS  # noqa: E402
from ai.scenarios_tools import SCENARIOS_TOOLS  # noqa: E402
from ai.scheduler_tools import SCHEDULER_TOOLS  # noqa: E402

TOOLS = TOOLS + NETWORKING_TOOLS + PERCEPTION_TOOLS + SCENARIOS_TOOLS + SCHEDULER_TOOLS

# ai_supercharger/, translation_engine/, entertainment_engine/,
# predictive_mind/, decision_engine_2.0/, advanced_personality/,
# empathy_engine/, language_generation/, penetration_testing/,
# threat_hunting/ - see ai/supercharger_tools.py's own docstring for
# the full list and the dotted-folder-name importlib workaround.
# Same bottom-import pattern as above, for the same circular-import
# reason.
from ai.supercharger_tools import SUPERCHARGER_TOOLS  # noqa: E402

TOOLS = TOOLS + SUPERCHARGER_TOOLS

# --- Offline knowledge base (knowledge_base/offline_wiki/) - local,
# no-internet Wikipedia-summary fallback for search_internet. Always
# present in the schema (unlike the ULTRON_DEVICES_ENABLED-style gated
# tools in ai/phase30_gated_tools.py) since it's read-only and harmless to
# offer - the safety/relevance gate lives inside search_offline_knowledge's
# handler (checks ULTRON_OFFLINE_KB_ENABLED) and its own tool description
# (last-resort framing), not at the schema level.
from ai.offline_kb_tools import OFFLINE_KB_TOOLS  # noqa: E402

TOOLS = TOOLS + OFFLINE_KB_TOOLS

# Autonomous internet-learning controls (status/start/stop/manual-trigger/
# topic queue) - see ai/autonomous_learning_tools.py and
# intelligence/ultron_advanced/autonomous_learning.py. Always present in
# the schema (read-only status + non-destructive on/off toggles for a
# background research job), same "always offer, gate is inside the
# feature itself" reasoning as OFFLINE_KB_TOOLS above.
from ai.autonomous_learning_tools import AUTOLEARN_TOOLS  # noqa: E402

TOOLS = TOOLS + AUTOLEARN_TOOLS

# multi_agent_swarm/ (agent_orchestrator, task_delegation, consensus_engine,
# swarm_memory, specialist_agents/*) - a real, fully-implemented package,
# genuinely built for Ultron, that had zero entries here despite
# core/assistant.py already instantiating it. Same "Unknown tool" gap
# class as every block above. See ai/multi_agent_swarm_tools.py.
from ai.multi_agent_swarm_tools import SWARM_TOOLS  # noqa: E402

TOOLS = TOOLS + SWARM_TOOLS

# Financial intelligence (finance/): expense tracking, per-category
# budgets with over/near-limit alerts, and a recurring stock/crypto price
# watcher with threshold alerts - see ai/finance_tools.py and finance/.
# A genuinely new capability, not present in the pre-upgrade tree. Always
# present in the schema (read-only reporting + local-state-only writes,
# no payments/bank access anywhere); market_watch's recurring scheduler
# is separately gated by ULTRON_MARKET_WATCH_ENABLED in core/assistant.py,
# same "always offer, gate is inside the feature itself" reasoning as
# AUTOLEARN_TOOLS above.
from ai.finance_tools import FINANCE_TOOLS  # noqa: E402

TOOLS = TOOLS + FINANCE_TOOLS

# Wellness tracking (wellness/): steps, water, sleep, workouts, and a
# simple 1-5 mood check-in, with user-set daily/weekly goals and
# consecutive-day streaks - see ai/wellness_tools.py and wellness/.
# Another genuinely new capability (grep for fitness/sleep/workout across
# the whole tree returned zero matches before this). Purely local
# logging - no wearable integration, no calorie/weight/diet tracking, no
# AI-generated targets. Always present in the schema, same "always
# offer" reasoning as FINANCE_TOOLS above.
from ai.wellness_tools import WELLNESS_TOOLS  # noqa: E402

TOOLS = TOOLS + WELLNESS_TOOLS

# Cross-device pairing (cross_device/): lets the user actually get a
# pairing code out of Ultron for the Android companion app - the
# servers (CompanionAPI/CompanionWebSocketServer) already ran, but
# nothing could trigger start_pairing() itself. See
# ai/cross_device_tools.py and cross_device/runtime.py. Schema
# visibility is gated inside cross_device_tools.py itself (empty list
# unless ULTRON_CROSS_DEVICE_ENABLED is on) - same "model never sees a
# tool it can't use" convention as ai/phase30_gated_tools.py.
from ai.cross_device_tools import CROSS_DEVICE_TOOLS  # noqa: E402

TOOLS = TOOLS + CROSS_DEVICE_TOOLS

TOOLS = _dedupe_tools_keep_last(TOOLS)
