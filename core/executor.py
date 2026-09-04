"""
Tool executor
=============
Maps a tool name + arguments dict (as produced by the model, see ai/prompts.py)
to a call against the windows/ facade (which itself delegates to files/,
browser/, automation/ etc.) and returns a JSON string result.
"""

import json
from typing import Dict

from windows import get_system_tools


def _workflow_engine():
    # Imported lazily: core.workflow_engine imports execute_tool from this
    # module, so importing it at module load time would be circular.
    from core.workflow_engine import get_workflow_engine

    return get_workflow_engine()


def _task_queue():
    from core.task_queue import get_task_queue

    return get_task_queue()


# Lazily-instantiated singletons for the newer agents/ai/memory/plugins
# modules, same pattern as _workflow_engine()/_task_queue() above - keeps
# execute_tool() itself free of heavy imports it may never need.
_singletons: Dict[str, object] = {}


def _get(key: str):
    if key not in _singletons:
        if key == "contacts_agent":
            from agents.contacts_agent import ContactsAgent

            _singletons[key] = ContactsAgent()
        elif key == "google_calendar":
            from connect.calendar import get_calendar

            _singletons[key] = get_calendar()
        elif key == "social_connect":
            from connect.social import get_social

            _singletons[key] = get_social()
        elif key == "calendar_agent":
            from agents.calendar_agent import CalendarAgent

            _singletons[key] = CalendarAgent()
        elif key == "task_agent":
            from agents.task_agent import TaskAgent

            _singletons[key] = TaskAgent()
        elif key == "health_agent":
            from agents.health_agent import HealthAgent

            _singletons[key] = HealthAgent()
        elif key == "security_agent":
            from agents.security_agent import SecurityAgent

            _singletons[key] = SecurityAgent()
        elif key == "email_agent":
            from agents.email_agent import EmailAgent

            _singletons[key] = EmailAgent()
        elif key == "web_agent":
            from agents.web_agent import WebAgent

            _singletons[key] = WebAgent()
        elif key == "episodic_memory":
            from memory.episodic_memory import EpisodicMemory

            _singletons[key] = EpisodicMemory()
        elif key == "semantic_memory":
            from memory.semantic_memory import SemanticMemory

            _singletons[key] = SemanticMemory()
        elif key == "procedural_memory":
            from memory.procedural_memory import ProceduralMemory

            _singletons[key] = ProceduralMemory()
        elif key == "emotional_memory":
            from memory.emotional_memory import EmotionalMemory

            _singletons[key] = EmotionalMemory()
        elif key == "rag_engine":
            from ai.rag_engine import RAGEngine

            _singletons[key] = RAGEngine()
        elif key == "chain_of_thought":
            from ai.chain_of_thought import ChainOfThought

            _singletons[key] = ChainOfThought()
        elif key == "marketplace":
            from plugins.marketplace.registry import PluginMarketplace

            _singletons[key] = PluginMarketplace()
        elif key == "mission_manager":
            from intelligence.mission_engine import get_mission_manager

            _singletons[key] = get_mission_manager()
        elif key == "tool_chain_optimizer":
            from ai.tool_chain_optimizer import get_tool_chain_optimizer

            _singletons[key] = get_tool_chain_optimizer()
        elif key == "capability_isolation":
            from security.capability_isolation import get_capability_isolation

            _singletons[key] = get_capability_isolation()
        elif key == "evidence_ledger":
            from intelligence.evidence_ledger import get_evidence_ledger

            _singletons[key] = get_evidence_ledger()
        elif key == "failure_pattern_engine":
            from learning_engine.failure_pattern_engine import get_failure_pattern_engine

            _singletons[key] = get_failure_pattern_engine()
        elif key == "knowledge_os":
            from intelligence.knowledge_os import get_knowledge_os

            _singletons[key] = get_knowledge_os()
        elif key == "resource_aware_engine":
            from intelligence.resource_intelligence import get_resource_aware_engine

            _singletons[key] = get_resource_aware_engine()
        elif key == "tool_benchmark_engine":
            from ai.tool_benchmark import get_tool_benchmark_engine

            _singletons[key] = get_tool_benchmark_engine()
        elif key == "conflict_resolver":
            from intelligence.conflict_resolution import get_conflict_resolver

            _singletons[key] = get_conflict_resolver()
        elif key == "workflow_graph_engine":
            from intelligence.workflow_graph import get_workflow_graph_engine

            _singletons[key] = get_workflow_graph_engine()
        elif key == "rpa_recorder":
            from automation.RPA.recorder import RPARecorder

            _singletons[key] = RPARecorder()
        elif key == "rpa_player":
            from automation.RPA.player import RPAPlayer

            _singletons[key] = RPAPlayer()
        elif key == "rpa_editor":
            from automation.RPA.editor import RPAEditor

            _singletons[key] = RPAEditor()
        elif key == "file_watcher":
            from automation.triggers.file_watcher import FileWatcher

            _singletons[key] = FileWatcher()
        elif key == "time_trigger":
            from automation.triggers.time_trigger import get_time_trigger

            _singletons[key] = get_time_trigger()
        elif key == "system_trigger":
            from automation.triggers.system_trigger import get_system_trigger

            _singletons[key] = get_system_trigger()
        elif key == "condition_evaluator":
            from automation.conditions.if_conditions import ConditionEvaluator

            _singletons[key] = ConditionEvaluator()
        elif key == "loop_runner":
            from automation.conditions.loops import LoopRunner

            _singletons[key] = LoopRunner()
        elif key == "scene_understanding":
            from vision.scene_understanding import get_scene_understanding

            _singletons[key] = get_scene_understanding()
        elif key == "form_recognizer":
            from vision.form_recognition import get_form_recognizer

            _singletons[key] = get_form_recognizer()
        elif key == "diagram_parser":
            from vision.diagram_parser import get_diagram_parser

            _singletons[key] = get_diagram_parser()
        elif key == "handwriting_recognizer":
            from vision.handwriting import get_handwriting_recognizer

            _singletons[key] = get_handwriting_recognizer()
        elif key == "vision_llm":
            from vision.vision_llm import get_vision_llm

            _singletons[key] = get_vision_llm()
        elif key == "screen_analyzer":
            from perception.screen_analyzer import get_screen_analyzer

            _singletons[key] = get_screen_analyzer()
        elif key == "voice_command_registry":
            from voice.voice_commands import get_voice_command_registry

            _singletons[key] = get_voice_command_registry()
        elif key == "speaker_recognizer":
            from voice.speaker_recognition import get_speaker_recognizer

            _singletons[key] = get_speaker_recognizer()
        elif key == "emotion_detector":
            from voice.emotion_detection import get_emotion_detector

            _singletons[key] = get_emotion_detector()
        elif key == "ultron_voice":
            from voice import get_voice

            _singletons[key] = get_voice()
        # Phase 18.9.2 self-management (bookkeeping only - no shell/restart
        # actually happens inside these modules themselves, see each
        # module's own docstring).
        elif key == "self_health_check":
            from heal.health_check import get_health_check

            _singletons[key] = get_health_check()
        elif key == "self_auto_fix":
            from heal.auto_fix import get_auto_fix

            _singletons[key] = get_auto_fix()
        elif key == "self_restart_log":
            from heal.restart import get_restart

            _singletons[key] = get_restart()
        elif key == "self_update_log":
            from heal.update_self import get_update_self

            _singletons[key] = get_update_self()
        elif key == "morning_brief":
            from proactive.morning_brief import get_morning_brief

            _singletons[key] = get_morning_brief()
        elif key == "evening_wrap":
            from proactive.evening_wrap import get_evening_wrap

            _singletons[key] = get_evening_wrap()
        elif key == "health_remind":
            from proactive.health_remind import get_health_remind

            _singletons[key] = get_health_remind()
        elif key == "meeting_prep":
            from proactive.meeting_prep import get_meeting_prep

            _singletons[key] = get_meeting_prep()
        elif key == "travel_alert":
            from proactive.travel_alert import get_travel_alert

            _singletons[key] = get_travel_alert()
        # Phase 18.6 AI agent personas (analyst/researcher/teacher/writer/
        # guard - coder.py deliberately NOT wired here, it duplicates the
        # already-connected write_code/review_code/explain_code tools
        # above almost exactly).
        elif key == "analyst_agent":
            from agents.analyst import AnalystAgent

            _singletons[key] = AnalystAgent()
        elif key == "researcher_agent":
            from agents.researcher import ResearcherAgent

            _singletons[key] = ResearcherAgent()
        elif key == "teacher_agent":
            from agents.teacher import TeacherAgent

            _singletons[key] = TeacherAgent()
        elif key == "writer_agent":
            from agents.writer import WriterAgent

            _singletons[key] = WriterAgent()
        elif key == "guard_agent":
            from agents.guard import GuardAgent

            _singletons[key] = GuardAgent()
        # Phase 18.7 automation: only call_phone.py is genuinely new -
        # CONNECT/email.py duplicates the already-wired agents/email_agent.py
        # (send_email/read_inbox/search_emails), CONNECT/whatsapp.py
        # duplicates the already-wired skills/communication/whatsapp.py
        # (send_whatsapp_message) AND apps/communication/whatsapp.py
        # (whatsapp_send_message/_by_name), and ACTIONS/send_message.py is
        # just mouse_click + type_text + press_key("enter") already
        # available as three separate existing tools - see
        # docs/TASK7_CALL_PHONE.md for the full reasoning. None of those
        # three are wired here to avoid handing the model duplicate tools
        # for the same job.
        elif key == "call_phone":
            from actions.call_phone import get_call_phone

            _singletons[key] = get_call_phone()
        else:
            raise KeyError(f"Unknown singleton: {key}")
    return _singletons[key]


def _resolve_and_call_phone(d: Dict) -> Dict:
    """Helper for the call_phone tool: accepts either a raw `number` or
    a contact `name` (looked up via agents/contacts_agent.py). Confirm
    check runs first regardless of which one was given, so an
    unconfirmed call never triggers a contacts lookup either."""
    if not d.get("confirm", False):
        return {"error": "This places a phone call. Call again with confirm=true to proceed."}

    number = d.get("number", "")
    if not number and d.get("name"):
        lookup = _get("contacts_agent").find_contact(d["name"])
        if lookup.get("error"):
            return {"success": False, "error": lookup["error"]}
        if not lookup.get("found"):
            return {
                "success": False,
                "error": f"No contact found named '{d['name']}'. " f"Use add_contact first, or give a number directly.",
            }
        number = lookup["contact"].get("phone", "")
        if not number:
            return {"success": False, "error": f"Contact '{d['name']}' has no phone number saved."}

    return _get("call_phone").call(number)


def execute_tool(tool_name: str, arguments: Dict) -> str:
    """Execute a tool and return JSON result."""
    tools = get_system_tools()

    tool_map = {
        "list_directory": lambda d: tools.list_directory(d.get("path", "~")),
        "find_folder": lambda d: tools.find_folder(d.get("folder_name", ""), d.get("search_path", "~")),
        "search_files": lambda d: tools.search_files(d.get("pattern", "*"), d.get("search_path", "~")),
        "read_file": lambda d: tools.read_file(d.get("file_path", "")),
        "get_file_info": lambda d: tools.get_file_info(d.get("file_path", "")),
        "run_command": lambda d: tools.run_command(d.get("command", "")),
        "get_system_info": lambda d: tools.get_system_info(),
        "open_application": lambda d: tools.open_application(d.get("app_name", "")),
        "close_application": lambda d: tools.close_application(d.get("app_name", "")),
        "list_running_apps": lambda d: tools.list_running_apps(),
        "activate_window": lambda d: tools.activate_window(d.get("window_title", "")),
        "click_ui_element": lambda d: tools.click_element(
            d.get("element_name", ""), window_title=d.get("window_title")
        ),
        "type_into_ui_element": lambda d: tools.type_into_element(
            d.get("element_name", ""), d.get("text", ""), window_title=d.get("window_title")
        ),
        "list_ui_elements": lambda d: tools.list_elements(
            d.get("window_title", ""), control_type=d.get("control_type")
        ),
        # Vision-LLM fallback (see vision/vision_llm.py) for on-screen
        # content the accessibility tree above can't see - canvas/web-
        # rendered UI, images, icons with no label.
        "describe_screen": lambda d: _get("vision_llm").describe_screen(
            d.get("question", "Describe what's currently on screen.")
        ),
        # locate_on_screen routes through perception/screen_analyzer.py
        # (not vision_llm directly) so behavior is identical no matter
        # which path called it - this tool used to have two live
        # implementations that disagreed: the AI tool-calling loop
        # (ai/tool_runtime.py's _DIRECT_HANDLERS, via
        # ai/perception_tools.py) always went through screen_analyzer's
        # event-emitting, graceful-error wrapper, while every other
        # caller of this tool_map (automation/RPA/player.py,
        # automation/workflow/workflow.py, automation/conditions/*.py,
        # automation/triggers/*.py, voice/voice_commands.py,
        # core/scheduler.py, core/planner.py, ai/local_router.py - see
        # each file's own execute_tool()/execute_tool_call() usage) hit
        # this raw vision_llm call instead, with no perception.screen_locate
        # event fired (autonomous_engine/action_pipeline's "did this step
        # already happen" logic depends on that event - see
        # screen_analyzer.py's own docstring) and a raised exception on
        # failure instead of a clean {"available": False, ...} result.
        # Same fix shape as describe_screen's own vision_llm/OCR fallback
        # already being centralized in screen_analyzer.py - locate() just
        # hadn't been pointed at from here yet.
        "locate_on_screen": lambda d: _get("screen_analyzer").locate(d.get("target", "")),
        "click_by_vision": lambda d: _get("vision_llm").click_on_screen(
            d.get("target", ""), double_click=d.get("double_click", False)
        ),
        "open_url": lambda d: tools.open_url(d.get("url", "")),
        "open_urls": lambda d: tools.open_urls(d.get("urls", [])),
        "list_chrome_tabs": lambda d: tools.list_chrome_tabs(),
        "close_chrome_tab": lambda d: tools.close_chrome_tab(d.get("tab", "")),
        "close_chrome_tabs": lambda d: tools.close_chrome_tabs(d.get("tabs", [])),
        "scroll_chrome": lambda d: tools.scroll_chrome(d.get("direction", "down"), d.get("amount", 300)),
        "chrome_navigate": lambda d: tools.chrome_navigate(d.get("action", "")),
        "type_in_chrome": lambda d: tools.type_in_chrome(d.get("text", "")),
        "chrome_keypress": lambda d: tools.chrome_keypress(d.get("key", "enter")),
        "youtube_search": lambda d: tools.youtube_search(d.get("query", "")),
        "youtube_play": lambda d: tools.youtube_play(d.get("query", "")),
        "youtube_control": lambda d: tools.youtube_control(d.get("action", "toggle")),
        "chrome_zoom": lambda d: tools.chrome_zoom(d.get("action", "in")),
        "open_file": lambda d: tools.open_file(d.get("file_path", "")),
        "set_volume": lambda d: tools.set_volume(d.get("level", 50)),
        "get_volume": lambda d: tools.get_volume(),
        "mute": lambda d: tools.mute(),
        "unmute": lambda d: tools.unmute(),
        "take_screenshot": lambda d: tools.take_screenshot(d.get("filename")),
        "get_battery_status": lambda d: tools.get_battery_status(),
        "empty_trash": lambda d: tools.empty_trash(),
        "sleep_display": lambda d: tools.sleep_display(),
        # File management
        "create_folder": lambda d: tools.create_folder(d.get("folder_path", "")),
        "create_file": lambda d: tools.create_file(d.get("file_path", ""), d.get("content", "")),
        "write_file": lambda d: tools.write_file(d.get("file_path", ""), d.get("content", ""), d.get("append", False)),
        "copy_file": lambda d: tools.copy_file(d.get("source", ""), d.get("destination", "")),
        "move_file": lambda d: tools.move_file(d.get("source", ""), d.get("destination", "")),
        "delete_file": lambda d: tools.delete_file(d.get("file_path", "")),
        "delete_folder": lambda d: tools.delete_folder(d.get("folder_path", "")),
        # Clipboard
        "get_clipboard": lambda d: tools.get_clipboard(),
        "set_clipboard": lambda d: tools.set_clipboard(d.get("text", "")),
        # System info & power
        "get_cpu_ram_usage": lambda d: tools.get_cpu_ram_usage(),
        "get_disk_usage": lambda d: tools.get_disk_usage(d.get("drive")),
        "get_ip_address": lambda d: tools.get_ip_address(),
        "lock_screen": lambda d: tools.lock_screen(),
        "shutdown_pc": lambda d: tools.shutdown_pc(d.get("confirm", False)),
        "restart_pc": lambda d: tools.restart_pc(d.get("confirm", False)),
        "sign_out": lambda d: tools.sign_out(d.get("confirm", False)),
        "cancel_shutdown": lambda d: tools.cancel_shutdown(),
        # Brightness
        "get_brightness": lambda d: tools.get_brightness(),
        "set_brightness": lambda d: tools.set_brightness(d.get("level", 50)),
        # System-wide media keys
        "media_play_pause": lambda d: tools.media_play_pause(),
        "media_next": lambda d: tools.media_next(),
        "media_previous": lambda d: tools.media_previous(),
        "media_volume_up": lambda d: tools.media_volume_up(),
        "media_volume_down": lambda d: tools.media_volume_down(),
        "media_mute": lambda d: tools.media_mute(),
        # Generic keyboard input (any focused window)
        "type_text": lambda d: tools.type_text(d.get("text", "")),
        "press_key": lambda d: tools.press_key(d.get("key", "enter")),
        # Weather & notes
        "get_weather": lambda d: tools.get_weather(d.get("location", "")),
        "save_note": lambda d: tools.save_note(d.get("text", "")),
        "read_notes": lambda d: tools.read_notes(),
        # PDF / Office / Compression
        "extract_pdf_text": lambda d: tools.extract_text(d.get("file_path", "")),
        "get_pdf_page_count": lambda d: tools.get_page_count(d.get("file_path", "")),
        "merge_pdfs": lambda d: tools.merge_pdfs(d.get("file_paths", []), d.get("output_path", "")),
        "create_pdf_from_text": lambda d: tools.create_pdf_from_text(
            d.get("file_path", ""), d.get("text", ""), d.get("title", "")
        ),
        "read_docx": lambda d: tools.read_docx(d.get("file_path", "")),
        "create_docx": lambda d: tools.create_docx(d.get("file_path", ""), d.get("content", ""), d.get("title", "")),
        "read_xlsx": lambda d: tools.read_xlsx(d.get("file_path", ""), d.get("sheet_name")),
        "create_xlsx": lambda d: tools.create_xlsx(d.get("file_path", ""), d.get("rows", [])),
        "compress_files": lambda d: tools.compress(d.get("source_path", ""), d.get("output_path")),
        "extract_archive": lambda d: tools.extract(d.get("archive_path", ""), d.get("output_dir")),
        # Process management
        "list_processes": lambda d: tools.list_processes(d.get("sort_by", "memory"), d.get("limit", 30)),
        "find_process": lambda d: tools.find_process(d.get("name", "")),
        "kill_process": lambda d: tools.kill_process(d.get("name"), d.get("pid"), confirm=d.get("confirm", False)),
        "get_process_info": lambda d: tools.get_process_info(d.get("pid")),
        # Services / startup / notifications / firewall / defender / explorer / powershell
        "list_services": lambda d: tools.list_services(d.get("filter_status")),
        "get_service_status": lambda d: tools.get_service_status(d.get("service_name", "")),
        "list_startup_programs": lambda d: tools.list_startup_programs(),
        "show_notification": lambda d: tools.show_notification(
            d.get("title", ""), d.get("message", ""), d.get("duration", 5)
        ),
        "get_firewall_status": lambda d: tools.get_firewall_status(),
        "get_defender_status": lambda d: tools.get_status(),
        "start_defender_scan": lambda d: tools.start_quick_scan(),
        "open_explorer_at": lambda d: tools.open_explorer(d.get("path", "~")),
        "reveal_file_in_explorer": lambda d: tools.reveal_file(d.get("file_path", "")),
        "run_powershell": lambda d: tools.run_powershell(d.get("script", "")),
        # Edge / Firefox
        "list_edge_tabs": lambda d: tools.list_edge_tabs(),
        "close_edge_tab": lambda d: tools.close_edge_tab(d.get("tab", "")),
        "scroll_edge": lambda d: tools.scroll_edge(d.get("direction", "down"), d.get("amount", 300)),
        "edge_navigate": lambda d: tools.edge_navigate(d.get("action", "")),
        "type_in_edge": lambda d: tools.type_in_edge(d.get("text", "")),
        "list_firefox_tabs": lambda d: tools.list_firefox_tabs(),
        "close_firefox_tab": lambda d: tools.close_firefox_tab(d.get("tab", "")),
        "scroll_firefox": lambda d: tools.scroll_firefox(d.get("direction", "down"), d.get("amount", 300)),
        "firefox_navigate": lambda d: tools.firefox_navigate(d.get("action", "")),
        "list_downloads": lambda d: tools.list_downloads(d.get("limit", 30)),
        "open_download": lambda d: tools.open_download(d.get("filename", "")),
        "get_download_history": lambda d: tools.get_download_history(d.get("browser", "chrome"), d.get("limit", 20)),
        # Mouse / macros / workflows
        "mouse_move": lambda d: tools.move_to(d.get("x", 0), d.get("y", 0)),
        "mouse_click": lambda d: tools.click(d.get("x"), d.get("y"), d.get("button", "left")),
        "mouse_scroll": lambda d: tools.scroll(d.get("amount", 0)),
        "start_macro_recording": lambda d: tools.start_recording(),
        "stop_macro_recording": lambda d: tools.stop_recording(d.get("macro_name", "")),
        "play_macro": lambda d: tools.play_macro(d.get("macro_name", ""), d.get("speed", 1.0)),
        "list_macros": lambda d: tools.list_macros(),
        "save_workflow": lambda d: tools.save_workflow(d.get("workflow_name", ""), d.get("steps", [])),
        "run_workflow": lambda d: tools.run_workflow(d.get("workflow_name", "")),
        "list_workflows": lambda d: tools.list_workflows(),
        # Memory: facts + similarity search
        "remember_fact": lambda d: tools.store(d.get("key", ""), d.get("value", ""), d.get("category", "general")),
        "recall_fact": lambda d: tools.get(d.get("key", ""), d.get("category", "general")),
        "search_facts": lambda d: tools.search(d.get("query", ""), d.get("category")),
        "forget_fact": lambda d: tools.forget(d.get("key", ""), d.get("category", "general")),
        "remember_for_search": lambda d: tools.add(d.get("text", ""), d.get("category", "general")),
        "search_memory": lambda d: tools.similarity_search(d.get("query", ""), d.get("top_k", 5)),
        # Vision: OCR
        "read_screen_text": lambda d: tools.read_screen(),
        # Vision: face / object / UI detection
        "detect_faces_on_screen": lambda d: tools.detect_faces_on_screen(),
        "detect_objects_on_screen": lambda d: tools.detect_objects_on_screen(d.get("confidence_threshold", 0.4)),
        "find_ui_text_regions": lambda d: tools.find_ui_text_regions(),
        # Coding agent
        "write_code": lambda d: tools.write_code(d.get("spec", ""), d.get("language")),
        "review_code": lambda d: tools.review_code(d.get("code", "")),
        "fix_code": lambda d: tools.fix_code(d.get("code", ""), d.get("error_message")),
        "explain_code": lambda d: tools.explain_code(d.get("code", "")),
        # Advanced workflows
        "save_advanced_workflow": lambda d: _workflow_engine().save_workflow(d.get("name", ""), d.get("steps", [])),
        "run_advanced_workflow": lambda d: (
            _workflow_engine().run_workflow_async(d.get("name", ""), d.get("stop_on_error", True))
            if d.get("run_in_background")
            else _workflow_engine().run_workflow(d.get("name", ""), d.get("stop_on_error", True))
        ),
        "list_advanced_workflows": lambda d: _workflow_engine().list_workflows(),
        # Background tasks
        "get_task_status": lambda d: _task_queue().get_status(d.get("task_id", "")),
        "list_background_tasks": lambda d: _task_queue().list_tasks(d.get("status")),
        # Calendar (agents/calendar_agent.py)
        "add_calendar_event": lambda d: _get("calendar_agent").add_event(
            d.get("title", ""), d.get("start_time", ""), d.get("end_time"), d.get("location", ""), d.get("notes", "")
        ),
        "list_calendar_events": lambda d: _get("calendar_agent").list_events(d.get("start_time"), d.get("end_time")),
        "upcoming_calendar_events": lambda d: _get("calendar_agent").upcoming_events(d.get("within_hours", 24)),
        "delete_calendar_event": lambda d: _get("calendar_agent").delete_event(d.get("event_id", "")),
        # Google Calendar (PHASE_18_7_AUTOMATION/CONNECT/calendar.py) - the
        # local calendar_agent above is offline/SQLite-only, this is a
        # genuinely different capability (real cloud sync to the user's
        # actual Google account, readable from their phone too), not a
        # duplicate, so it gets its own distinctly-named tools rather than
        # being folded into add_calendar_event/list_calendar_events.
        # Needs GOOGLE_CALENDAR_ACCESS_TOKEN in .env - returns an empty
        # list / {"success": False} rather than erroring if not configured.
        "google_calendar_list_events": lambda d: _get("google_calendar").list_upcoming(d.get("num", 5)),
        "google_calendar_create_event": lambda d: _get("google_calendar").create_event(
            d.get("summary", ""), d.get("start_iso", ""), d.get("end_iso", ""), d.get("description", "")
        ),
        # Contacts (agents/contacts_agent.py) - local name->number/email
        # store, mainly so call_phone (below) and other tools can be given
        # a name instead of a raw number.
        "add_contact": lambda d: _get("contacts_agent").add_contact(
            d.get("name", ""), d.get("phone", ""), d.get("email", ""), d.get("notes", "")
        ),
        "find_contact": lambda d: _get("contacts_agent").find_contact(d.get("name", "")),
        "list_contacts": lambda d: _get("contacts_agent").list_contacts(),
        "delete_contact": lambda d: _get("contacts_agent").delete_contact(d.get("name", "")),
        # Social (PHASE_18_7_AUTOMATION/CONNECT/social.py) - deliberately
        # narrow webhook fan-out (Slack/Discord/Zapier etc. via
        # SOCIAL_WEBHOOK_<NAME> env vars), not native Twitter/Instagram/
        # LinkedIn OAuth posting - see that module's own docstring. This
        # one genuinely isn't a duplicate of anything else already wired.
        "post_to_social": lambda d: _get("social_connect").post(d.get("message", ""), d.get("platforms")),
        # To-do list (agents/task_agent.py)
        "add_todo": lambda d: _get("task_agent").add_todo(d.get("text", ""), d.get("priority", "normal"), d.get("due")),
        "list_todos": lambda d: _get("task_agent").list_todos(d.get("include_done", False)),
        "complete_todo": lambda d: _get("task_agent").complete_todo(d.get("todo_id", "")),
        "delete_todo": lambda d: _get("task_agent").delete_todo(d.get("todo_id", "")),
        # Health (agents/health_agent.py)
        "log_water": lambda d: _get("health_agent").log_water(d.get("ml", 0)),
        "log_sleep": lambda d: _get("health_agent").log_sleep(d.get("hours", 0), d.get("note", "")),
        "log_exercise": lambda d: _get("health_agent").log_exercise(d.get("minutes", 0), d.get("note", "")),
        "health_daily_summary": lambda d: _get("health_agent").daily_summary(),
        # Security (agents/security_agent.py)
        "check_password_strength": lambda d: _get("security_agent").check_password_strength(d.get("password", "")),
        "generate_secure_password": lambda d: _get("security_agent").generate_secure_password(
            d.get("length", 16), d.get("symbols", True)
        ),
        "audit_file_permissions": lambda d: _get("security_agent").audit_file_permissions(d.get("path", "")),
        # Email (agents/email_agent.py)
        "send_email": lambda d: _get("email_agent").send_email(
            d.get("to", ""), d.get("subject", ""), d.get("body", ""), d.get("cc")
        ),
        "read_inbox": lambda d: _get("email_agent").read_inbox(d.get("limit", 10), d.get("unread_only", False)),
        "search_emails": lambda d: _get("email_agent").search_emails(d.get("query", ""), d.get("limit", 10)),
        # Episodic / semantic / emotional memory
        "record_event": lambda d: _get("episodic_memory").record_event(
            d.get("event", ""), d.get("context", ""), d.get("tags", "")
        ),
        "recall_recent_events": lambda d: _get("episodic_memory").recent_events(d.get("limit", 20)),
        "define_concept": lambda d: _get("semantic_memory").add_concept(d.get("concept", ""), d.get("definition", "")),
        "recall_concept": lambda d: _get("semantic_memory").define(d.get("concept", "")),
        "log_mood": lambda d: _get("emotional_memory").log_mood(
            d.get("emotion", ""), d.get("intensity", 3), d.get("note", "")
        ),
        "get_mood_trend": lambda d: _get("emotional_memory").mood_trend(d.get("days", 7)),
        # RAG + deep reasoning
        "rag_answer": lambda d: _get("rag_engine").answer(d.get("question", ""), d.get("top_k", 5)),
        "reason_deeply": lambda d: _get("chain_of_thought").run(d.get("question", ""), d.get("max_subquestions", 5)),
        # Plugin marketplace
        "list_available_plugins": lambda d: _get("marketplace").list_available(),
        "install_plugin": lambda d: _get("marketplace").install(d.get("name", "")),
        # App control (skills/app_control/*) - higher-level than open_application/close_application above
        "find_app": lambda d: tools.find_app(d.get("query", "")),
        "app_status": lambda d: tools.app_status(d.get("app_name", "")),
        "restart_app": lambda d: tools.restart_app(d.get("app_name", "")),
        "minimize_app": lambda d: tools.minimize_app(d.get("app_name", "")),
        "maximize_app": lambda d: tools.maximize_app(d.get("app_name", "")),
        "focus_app": lambda d: tools.focus_app(d.get("app_name", "")),
        "close_all_by_category": lambda d: tools.close_all_by_category(d.get("category", "")),
        "kill_unresponsive_apps": lambda d: tools.kill_unresponsive_apps(),
        "list_apps_by_category": lambda d: tools.list_by_category(d.get("category", "")),
        # Window manager (windows/window_manager.py)
        "list_windows": lambda d: tools.list_windows(),
        "get_window_geometry": lambda d: tools.get_window_geometry(d.get("window_title", "")),
        "move_window": lambda d: tools.move_window(d.get("window_title", ""), d.get("x", 0), d.get("y", 0)),
        "resize_window": lambda d: tools.resize_window(
            d.get("window_title", ""), d.get("width", 800), d.get("height", 600)
        ),
        "snap_window": lambda d: tools.snap_window(d.get("window_title", ""), d.get("zone", "left")),
        "minimize_window": lambda d: tools.minimize_window(d.get("window_title", "")),
        "maximize_window": lambda d: tools.maximize_window(d.get("window_title", "")),
        "restore_window": lambda d: tools.restore_window(d.get("window_title", "")),
        "close_window": lambda d: tools.close_window(d.get("window_title", "")),
        "bring_window_to_front": lambda d: tools.bring_to_front(d.get("window_title", "")),
        "tile_windows": lambda d: tools.tile_windows(d.get("window_titles", [])),
        # Virtual desktops (windows/virtual_desktop.py)
        "list_virtual_desktops": lambda d: tools.list_desktops(),
        "create_virtual_desktop": lambda d: tools.create_desktop(),
        "switch_virtual_desktop": lambda d: tools.switch_to(d.get("desktop_number", 1)),
        "switch_next_virtual_desktop": lambda d: tools.switch_next(),
        "switch_previous_virtual_desktop": lambda d: tools.switch_previous(),
        "close_virtual_desktop": lambda d: tools.close_current_desktop(),
        "move_window_to_desktop": lambda d: tools.move_window_to_desktop(
            d.get("window_title", ""), d.get("desktop_number", 1)
        ),
        # Power management (windows/power_management.py) - plans/sleep, distinct from shutdown_pc/restart_pc above
        "sleep_now": lambda d: tools.sleep_now(),
        "hibernate_now": lambda d: tools.hibernate_now(),
        "list_power_plans": lambda d: tools.list_power_plans(),
        "get_active_power_plan": lambda d: tools.get_active_power_plan(),
        "set_power_plan": lambda d: tools.set_power_plan(d.get("plan_name", "")),
        "set_sleep_timeout": lambda d: tools.set_sleep_timeout(d.get("minutes", 15), d.get("on_battery", False)),
        "set_screen_timeout": lambda d: tools.set_screen_timeout(d.get("minutes", 10), d.get("on_battery", False)),
        "enable_battery_saver": lambda d: tools.enable_battery_saver(),
        "disable_battery_saver": lambda d: tools.disable_battery_saver(),
        # Accessibility (windows/accessibility.py)
        "toggle_narrator": lambda d: tools.toggle_narrator(),
        "set_high_contrast": lambda d: tools.set_high_contrast(d.get("enabled", True)),
        "toggle_magnifier": lambda d: tools.toggle_magnifier(),
        "set_sticky_keys": lambda d: tools.set_sticky_keys(d.get("enabled", True)),
        "announce": lambda d: tools.announce(d.get("text", "")),
        # Bookmarks (browser/bookmark_manager.py)
        "list_bookmarks": lambda d: tools.list_bookmarks(d.get("browser", "chrome")),
        "search_bookmarks": lambda d: tools.search_bookmarks(d.get("query", ""), d.get("browser", "chrome")),
        "add_bookmark": lambda d: tools.add_bookmark(
            d.get("name", ""), d.get("url", ""), d.get("browser", "chrome"), d.get("folder", "Bookmarks bar")
        ),
        "delete_bookmark": lambda d: tools.delete_bookmark(d.get("name", ""), d.get("browser", "chrome")),
        # History analysis (browser/history_analyzer.py)
        "recent_browser_history": lambda d: tools.recent_history(d.get("browser", "chrome"), d.get("limit", 30)),
        "most_visited_sites": lambda d: tools.most_visited(d.get("browser", "chrome"), d.get("limit", 15)),
        "top_browsed_domains": lambda d: tools.top_domains(
            d.get("browser", "chrome"), d.get("limit", 15), d.get("days", 30)
        ),
        "browsing_activity_by_hour": lambda d: tools.activity_by_hour(d.get("browser", "chrome"), d.get("days", 30)),
        "search_browser_history": lambda d: tools.search_history(
            d.get("query", ""), d.get("browser", "chrome"), d.get("limit", 30)
        ),
        # Cross-browser tabs (browser/tab_manager.py)
        "list_all_tabs": lambda d: tools.list_all_tabs(),
        "close_tab_in_browser": lambda d: tools.close_tab(d.get("tab", ""), d.get("browser", "chrome")),
        "close_tabs_matching": lambda d: tools.close_tabs_matching(d.get("query", "")),
        # Form filler (browser/form_filler.py)
        "fill_form_field": lambda d: tools.fill_field(d.get("value", ""), d.get("press_tab_after", True)),
        "fill_form_sequence": lambda d: tools.fill_sequence(d.get("values", [])),
        "submit_form": lambda d: tools.submit_form(),
        "save_form_profile": lambda d: tools.save_profile(d.get("profile_name", ""), d.get("fields", {})),
        "autofill_form": lambda d: tools.autofill_from_profile(d.get("profile_name", ""), d.get("field_order", [])),
        # RPA (automation/RPA/*)
        "rpa_start_recording": lambda d: _get("rpa_recorder").start_recording(),
        "rpa_stop_recording": lambda d: _get("rpa_recorder").stop_recording(d.get("script_name", "")),
        "rpa_add_step": lambda d: _get("rpa_recorder").add_step(
            d.get("step_type", ""), **{k: v for k, v in d.items() if k != "step_type"}
        ),
        "rpa_play": lambda d: _get("rpa_player").play(d.get("script_name", ""), d.get("speed", 1.0), d.get("loop", 1)),
        "rpa_dry_run": lambda d: _get("rpa_player").dry_run(d.get("script_name", "")),
        "rpa_list_scripts": lambda d: _get("rpa_player").list_scripts(),
        "rpa_insert_step": lambda d: _get("rpa_editor").insert_step(
            d.get("script_name", ""), d.get("index", 0), d.get("step", {})
        ),
        "rpa_delete_step": lambda d: _get("rpa_editor").delete_step(d.get("script_name", ""), d.get("step_id", "")),
        "rpa_delete_script": lambda d: _get("rpa_editor").delete_script(d.get("script_name", "")),
        # Triggers (automation/triggers/*)
        "watch_file": lambda d: _get("file_watcher").watch(
            d.get("path", ""), d.get("tool_name"), d.get("arguments", {}), d.get("events"), d.get("recursive", False)
        ),
        "stop_watching_file": lambda d: _get("file_watcher").stop_watching(d.get("watch_id", "")),
        "list_file_watches": lambda d: _get("file_watcher").list_watches(),
        "add_daily_trigger": lambda d: _get("time_trigger").add_daily_trigger(
            d.get("hour", 9),
            d.get("minute", 0),
            d.get("tool_name", ""),
            d.get("arguments", {}),
            d.get("days"),
            d.get("label", ""),
        ),
        "add_interval_trigger": lambda d: _get("time_trigger").add_interval_trigger(
            d.get("interval_seconds", 3600), d.get("tool_name", ""), d.get("arguments", {}), d.get("label", "")
        ),
        "remove_time_trigger": lambda d: _get("time_trigger").remove_trigger(d.get("trigger_id", "")),
        "list_time_triggers": lambda d: _get("time_trigger").list_triggers(),
        "on_battery_threshold": lambda d: _get("system_trigger").on_battery_threshold(
            d.get("below_percent", 20),
            d.get("tool_name", ""),
            d.get("arguments", {}),
            d.get("only_when_discharging", True),
            d.get("label", ""),
        ),
        "on_process_start_trigger": lambda d: _get("system_trigger").on_process_start(
            d.get("process_name", ""), d.get("tool_name", ""), d.get("arguments", {}), d.get("label", "")
        ),
        "on_process_stop_trigger": lambda d: _get("system_trigger").on_process_stop(
            d.get("process_name", ""), d.get("tool_name", ""), d.get("arguments", {}), d.get("label", "")
        ),
        "list_system_triggers": lambda d: _get("system_trigger").list_triggers(),
        "remove_system_trigger": lambda d: _get("system_trigger").remove_trigger(d.get("trigger_id", "")),
        # Conditions & loops (automation/conditions/*)
        "evaluate_condition": lambda d: _get("condition_evaluator").evaluate(d.get("condition", {})),
        "run_if_condition": lambda d: _get("condition_evaluator").run_if(
            d.get("condition", {}), d.get("then_step", {}), d.get("else_step")
        ),
        "loop_repeat": lambda d: _get("loop_runner").repeat(
            d.get("tool_name", ""), d.get("arguments", {}), d.get("times", 1), d.get("delay_seconds", 0.0)
        ),
        "loop_while": lambda d: _get("loop_runner").while_condition(
            d.get("condition", {}),
            d.get("tool_name", ""),
            d.get("arguments", {}),
            d.get("max_iterations", 100),
            d.get("delay_seconds", 1.0),
        ),
        "loop_for_each": lambda d: _get("loop_runner").for_each(
            d.get("tool_name", ""), d.get("arguments", {}), d.get("items", []), d.get("item_arg_name", "item")
        ),
        # Vision Phase 4: scene understanding, form/diagram parsing, handwriting
        "describe_screen_regions": lambda d: _get("scene_understanding").describe_screen(
            d.get("include_objects", True)
        ),
        "detect_form_fields": lambda d: _get("form_recognizer").detect_fields(),
        "parse_diagram": lambda d: _get("diagram_parser").parse(),
        "read_handwriting": lambda d: _get("handwriting_recognizer").read(file_path=d.get("file_path")),
        # Voice Phase 4: custom voice command shortcuts
        "add_voice_command": lambda d: _get("voice_command_registry").add_command(
            d.get("phrase", ""), d.get("tool_name", ""), d.get("arguments", {}), d.get("label", "")
        ),
        "remove_voice_command": lambda d: _get("voice_command_registry").remove_command(d.get("phrase", "")),
        "list_voice_commands": lambda d: _get("voice_command_registry").list_commands(),
        # Voice Phase 4: speaker recognition (records from the mic itself)
        "enroll_speaker_voice": lambda d: _get("speaker_recognizer").enroll_from_mic(
            d.get("name", ""), d.get("duration", 4.0)
        ),
        "identify_speaker_from_mic": lambda d: _get("speaker_recognizer").identify_from_mic(d.get("duration", 4.0)),
        "list_enrolled_speakers": lambda d: _get("speaker_recognizer").list_speakers(),
        "forget_speaker": lambda d: _get("speaker_recognizer").forget_speaker(d.get("name", "")),
        # Voice Phase 4: emotion detection
        "detect_voice_emotion": lambda d: _get("emotion_detector").analyze_from_mic(d.get("duration", 4.0)),
        "analyze_text_sentiment": lambda d: _get("emotion_detector").analyze_text_sentiment(d.get("text", "")),
        # Voice Phase 9: multi-engine voice stack - runtime switching
        "set_tts_engine": lambda d: (
            _get("ultron_voice").set_engine(d.get("engine", "edge"))
            or {"success": True, "engine": d.get("engine", "edge")}
        ),
        "list_voice_engines": lambda d: {
            "tts_engines": ["edge", "gtts", "pyttsx3"],
            "stt_engines": ["auto", "cloud", "local", "vosk"],
            "wakeword_engines": ["openwakeword", "stt"],
        },
        # NOTE: Phase 18.9.2 self-management (health/auto-fix/restart/
        # version, morning/evening briefs, health reminders, meeting prep,
        # travel alerts - 18 tools) and Phase 18.6 AI agent personas
        # (analyst/researcher/teacher/writer/guard - 9 tools) used to have
        # a duplicate copy of their dispatch lambdas here. Removed
        # (2026-09-01 dead-code audit): all 27 names are already registered
        # in ai/tools_schema.py and dispatched via ai/self_management_tools.py
        # + ai/agents_tools.py's DIRECT_HANDLERS (merged into
        # ai/tool_runtime.py's _DIRECT_HANDLERS, which execute_tool_call()
        # checks before ever reaching this tool_map), so this copy was
        # 100% unreachable - confirmed via cross-reference, not just unused.
        # Phone call (PHASE_18_7_AUTOMATION/ACTIONS/call_phone.py) - real-
        # world action, safety-gated the same way shutdown_pc/restart_pc/
        # kill_process are: requires confirm=true, otherwise returns an
        # error asking for it instead of placing the call. Now also
        # registered in core/permissions.py's DESTRUCTIVE_TOOLS, so
        # ActionPipeline gates it centrally too (belt-and-suspenders with
        # this inline check, not a replacement for it).
        # Accepts a contact `name` instead of a raw `number` - resolves it
        # via agents/contacts_agent.py first. An unknown or ambiguous name
        # fails closed (never falls back to a guessed number).
        "call_phone": lambda d: _resolve_and_call_phone(d),
        # --- P1: Mission Persistence Engine (intelligence/mission_engine/) ---
        "create_mission": lambda d: _get("mission_manager").create_mission(
            d.get("title", ""), d.get("description", ""), d.get("context")
        ),
        "checkpoint_mission": lambda d: _get("mission_manager").checkpoint(
            d.get("mission_id", ""), d.get("note", ""), d.get("state")
        ),
        "list_active_missions": lambda d: _get("mission_manager").list_active_missions(),
        "get_resumable_mission": lambda d: (_get("mission_manager").get_resumable_mission() or {"resumable": False}),
        "resume_mission": lambda d: (
            _get("mission_manager").resume_mission(d.get("mission_id", "")) or {"error": "mission not found"}
        ),
        "pause_mission": lambda d: {"success": _get("mission_manager").pause_mission(d.get("mission_id", ""))},
        "complete_mission": lambda d: {"success": _get("mission_manager").complete_mission(d.get("mission_id", ""))},
        "abandon_mission": lambda d: {"success": _get("mission_manager").abandon_mission(d.get("mission_id", ""))},
        # --- P1: Intelligent Tool-Chain Optimizer (ai/tool_chain_optimizer.py) ---
        "rank_tool_candidates": lambda d: {"ranked": _get("tool_chain_optimizer").rank_tools(d.get("candidates", []))},
        "optimize_tool_chain": lambda d: _get("tool_chain_optimizer").optimize_chain(d.get("tools", [])),
        "get_tool_reliability_report": lambda d: {"tools": _get("tool_chain_optimizer").get_report(d.get("limit", 20))},
        # --- P1: Capability Isolation / Fine-Grained Permissions (security/capability_isolation.py) ---
        "check_capability_access": lambda d: _get("capability_isolation").check(
            d.get("tool_name", ""), d.get("arguments")
        ),
        "set_isolation_profile": lambda d: {
            "success": _get("capability_isolation").set_active_profile(d.get("profile", ""))
        },
        "get_isolation_policy": lambda d: {
            "active_profile": _get("capability_isolation").get_active_profile(),
            "policy": _get("capability_isolation").get_policy(d.get("profile")),
        },
        "set_capability_scope_policy": lambda d: {
            "success": _get("capability_isolation").set_scope_policy(
                d.get("profile", ""), d.get("scope", ""), d.get("mode", "")
            )
        },
        # --- P2: Evidence Ledger & Confidence Tracking (intelligence/evidence_ledger/) ---
        "log_claim_check": lambda d: _get("evidence_ledger").log_claim(
            d.get("claim", ""),
            d.get("verdict", "unverified"),
            float(d.get("confidence", 0.0)),
            d.get("evidence"),
            d.get("context", ""),
        ),
        "record_evidence_outcome": lambda d: {
            "success": _get("evidence_ledger").record_outcome(
                d.get("entry_id", ""), d.get("outcome", ""), d.get("note", "")
            )
        },
        "why_did_you_believe": lambda d: (
            _get("evidence_ledger").why_did_you_believe(d.get("claim", "")) or {"found": False}
        ),
        "get_source_reliability": lambda d: _get("evidence_ledger").get_source_reliability(d.get("source", "")),
        "get_recent_evidence_entries": lambda d: {
            "entries": _get("evidence_ledger").get_recent_entries(d.get("limit", 20))
        },
        "get_untrustworthy_sources": lambda d: {"sources": _get("evidence_ledger").get_untrustworthy_sources()},
        # --- P2: Failure Pattern Learning Engine (learning_engine/failure_pattern_engine.py) ---
        "check_tool_failure_risk": lambda d: _get("failure_pattern_engine").check_risk(d.get("tool_name", "")),
        "get_failure_patterns": lambda d: {
            "patterns": _get("failure_pattern_engine").get_patterns(d.get("tool_name"), d.get("limit", 20))
        },
        "get_failure_pattern_report": lambda d: _get("failure_pattern_engine").get_report(d.get("limit", 15)),
        # --- P3: Unified Personal Knowledge OS (intelligence/knowledge_os/) ---
        "remember_subject_fact": lambda d: _get("knowledge_os").remember_fact(
            d.get("subject", ""),
            d.get("fact_text", ""),
            d.get("predicate", "is"),
            d.get("source", "user"),
            float(d.get("confidence", 0.8)),
        ),
        "get_unified_knowledge_view": lambda d: _get("knowledge_os").get_unified_view(d.get("subject", "")),
        "search_knowledge": lambda d: _get("knowledge_os").search(d.get("query", ""), d.get("limit", 20)),
        "get_knowledge_freshness_report": lambda d: _get("knowledge_os").get_freshness_report(
            float(d.get("max_age_days", 7)) * 86400
        ),
        # --- P3: Resource-Aware Intelligence Engine (intelligence/resource_intelligence/) ---
        "recommend_execution_tier": lambda d: _get("resource_aware_engine").recommend_execution_tier(
            d.get("task_type", ""), d.get("estimated_cost", "medium")
        ),
        "track_task_resource_cost": lambda d: _get("resource_aware_engine").track_task_execution(
            d.get("task_type", ""),
            float(d.get("duration_ms", 0)),
            float(d.get("cpu_before", 0)),
            float(d.get("cpu_after", 0)),
            float(d.get("mem_before", 0)),
            float(d.get("mem_after", 0)),
        ),
        "get_resource_intelligence_report": lambda d: _get("resource_aware_engine").get_resource_report(),
        # --- P4: Automatic Tool Benchmarking & Reliability Scoring (ai/tool_benchmark/) ---
        "record_tool_benchmark": lambda d: (
            _get("tool_benchmark_engine").record(
                d.get("tool_name", ""), float(d.get("duration_ms", 0)), bool(d.get("success", True))
            )
            or {"recorded": True}
        ),
        "get_tool_benchmark": lambda d: _get("tool_benchmark_engine").get_benchmark(d.get("tool_name", "")),
        "get_tool_benchmark_report": lambda d: _get("tool_benchmark_engine").get_report(d.get("limit", 20)),
        "get_degrading_tools": lambda d: {"tools": _get("tool_benchmark_engine").get_degrading_tools()},
        # --- P4: Conflict Resolution Engine (intelligence/conflict_resolution/) ---
        "detect_source_conflict": lambda d: _get("conflict_resolver").detect_conflict(
            d.get("subject", ""),
            d.get("claim_a", ""),
            d.get("source_a", ""),
            d.get("claim_b", ""),
            d.get("source_b", ""),
        ),
        "auto_resolve_conflict": lambda d: _get("conflict_resolver").auto_resolve(d.get("conflict_id", "")),
        "manual_resolve_conflict": lambda d: _get("conflict_resolver").manual_resolve(
            d.get("conflict_id", ""), d.get("resolved_source", ""), d.get("note", "")
        ),
        "list_open_conflicts": lambda d: {"conflicts": _get("conflict_resolver").list_open_conflicts(d.get("subject"))},
        "get_conflict_report": lambda d: _get("conflict_resolver").get_conflict_report(d.get("limit", 20)),
        # --- P5: Personal Workflow Graph & Automation Discovery (intelligence/workflow_graph/) ---
        "register_workflow_graph_node": lambda d: _get("workflow_graph_engine").register_workflow(
            d.get("name", ""), d.get("tools_used", [])
        ),
        "link_workflow_sequence": lambda d: _get("workflow_graph_engine").link_sequence(
            d.get("workflow_a", ""), d.get("workflow_b", "")
        ),
        "discover_automation_opportunities": lambda d: {
            "opportunities": _get("workflow_graph_engine").discover_automation_opportunities(
                float(d.get("min_weight", 2))
            )
        },
        "get_workflow_graph_neighbors": lambda d: _get("workflow_graph_engine").get_workflow_neighbors(
            d.get("name", "")
        ),
        "get_workflow_graph_summary": lambda d: _get("workflow_graph_engine").get_graph_summary(),
    }

    if tool_name not in tool_map:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    result = tool_map[tool_name](arguments)
    return json.dumps(result, indent=2)
