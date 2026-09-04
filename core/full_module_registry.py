"""
core/full_module_registry.py
=============================
Central auto-wiring for every previously-unwired module found in the
Ultron_Networking_Perception_Scenarios_Scheduler_Wired deep scan.
Two passes were run: Round 1 caught modules with a zero-arg get_*()
singleton factory (the codebase's existing lazy-loader convention -
see skills/__init__.py, automation/__init__.py). Round 2 caught
modules with no such factory but whose main class takes no required
constructor args (dataclasses and abstract/ABC classes excluded, and
where a file had several classes the one whose name matches the
filename, or with the most methods, was picked as "the" class).

Two independent .env flags gate what gets loaded:

    ULTRON_SAFE_MODULES_ENABLED    default: true
        Modules with no shell/registry/network/credential/hook/screen-
        control footprint (pure logic, memory, perception helpers,
        UI widgets, reasoning, per-app automation wrappers with no
        destructive default behaviour). Safe to leave on.

    ULTRON_UNSAFE_MODULES_ENABLED  default: false
        Modules that can execute shell commands, touch the Windows
        registry, control mouse/keyboard, read/write clipboard, open
        network sockets, drive a browser, or handle credentials/
        tokens/LLM API clients. OFF by default. Set
        ULTRON_UNSAFE_MODULES_ENABLED=true in .env ONLY if you trust
        this machine/user fully - this switches on real system-
        control capability across all modules in this list at once.

Every entry is (dotted_module_path, entry_point_name, kind) where
kind is "func" (call entry_point_name() with no args) or "class"
(instantiate entry_point_name() with no args). Loading is wrapped
per-module in try/except so one broken or dependency-missing module
never blocks startup or the rest of the registry - it's just skipped
and logged, not raised.

~236 files remain genuinely un-auto-wireable: their constructors need
real arguments (a driver path, a config object, an API key, a device
handle, etc.) that can't be safely guessed, so wiring them means
reading each one and deciding what to pass in - left for hand-wiring.

Call wire_all_modules() once during startup (see core/assistant.py).
"""

import os
import logging
import importlib

logger = logging.getLogger("ultron.full_module_registry")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


SAFE_MODULES = [
    ("adaptive_ui.gesture_controller", "get_gesture_controller", "func"),
    ("adaptive_ui.holographic_orb", "get_holographic_orb", "func"),
    ("adaptive_ui.multi_modal_input", "get_fuser", "func"),
    ("advanced_memory.memory_consolidator", "get_consolidator", "func"),
    ("advanced_memory.semantic_memory", "get_advanced_semantic_memory", "func"),
    ("advanced_memory.spatial_memory", "get_spatial_memory", "func"),
    ("advanced_memory.temporal_memory", "get_temporal_memory", "func"),
    ("computer_vision.anomaly_detector", "get_anomaly_detector", "func"),
    ("computer_vision.scene_understanding", "get_continuous_scene_understanding", "func"),
    ("display.danger_alert", "get_danger_alert", "func"),
    ("display.face_label", "get_face_label", "func"),
    ("display.orb", "get_orb", "func"),
    ("display.price_tag", "get_price_tag", "func"),
    ("ears.always_listen", "get_always_listen", "func"),
    ("ears.multi_voice", "get_multi_voice", "func"),
    ("ears.noise_filter", "get_noise_filter", "func"),
    ("eyes.face_scanner", "get_face_scanner", "func"),
    ("eyes.night_eye", "get_night_eye", "func"),
    ("eyes.object_finder", "get_object_finder", "func"),
    ("eyes.text_reader", "get_text_reader", "func"),
    ("eyes.threat_sense", "get_threat_sense", "func"),
    ("intelligence.conversation_layer.barge_in_detector", "get_barge_in_detector", "func"),
    ("intelligence.conversation_layer.continuity_tracker", "get_continuity_tracker", "func"),
    ("intelligence.conversation_layer.conversation_engine", "get_conversation_engine", "func"),
    ("intelligence.conversation_layer.filler_generator", "get_filler_generator", "func"),
    ("intelligence.conversation_layer.response_timer", "get_response_timer", "func"),
    ("intelligence.intent_prediction.context_intent_mapper", "get_context_intent_mapper", "func"),
    ("intelligence.intent_prediction.intent_confidence", "get_intent_confidence", "func"),
    ("intelligence.intent_prediction.intent_predictor", "get_intent_predictor", "func"),
    ("intelligence.intent_prediction.next_action_predictor", "get_next_action_predictor", "func"),
    ("intelligence.intent_prediction.pattern_analyzer", "get_pattern_analyzer", "func"),
    ("intelligence.predictive_preparation.app_preloader", "get_app_preloader", "func"),
    ("intelligence.predictive_preparation.context_preloader", "get_context_preloader", "func"),
    ("intelligence.predictive_preparation.model_preloader", "get_model_preloader", "func"),
    ("intelligence.predictive_preparation.next_task_predictor", "get_next_task_predictor", "func"),
    ("intelligence.predictive_preparation.predictive_engine", "get_predictive_engine", "func"),
    ("intelligence.predictive_preparation.resource_optimizer", "get_resource_optimizer", "func"),
    ("intelligence.proactive_intelligence.conversation_initiator", "get_conversation_initiator", "func"),
    ("intelligence.proactive_intelligence.event_detector", "get_event_detector", "func"),
    ("intelligence.proactive_intelligence.notification_manager", "get_notification_manager", "func"),
    ("intelligence.proactive_intelligence.proactive_engine", "get_proactive_engine", "func"),
    ("intelligence.proactive_intelligence.suggestion_generator", "get_suggestion_generator", "func"),
    ("intelligence.proactive_intelligence.urgency_calculator", "get_urgency_calculator", "func"),
    ("intelligence.skill_builder.skill_builder_engine", "get_skill_builder_engine", "func"),
    ("intelligence.skill_builder.skill_generator", "get_skill_generator", "func"),
    ("intelligence.skill_builder.skill_improver", "get_skill_improver", "func"),
    ("intelligence.skill_builder.workflow_analyzer", "get_workflow_analyzer", "func"),
    ("intelligence.skill_builder.workflow_recorder", "get_workflow_recorder", "func"),
    ("intelligence.smart_answer_reader.adaptive_formatter", "get_adaptive_formatter", "func"),
    ("intelligence.smart_answer_reader.answer_reader_engine", "get_answer_reader_engine", "func"),
    ("intelligence.smart_answer_reader.length_detector", "get_length_detector", "func"),
    ("intelligence.smart_answer_reader.point_extractor", "get_point_extractor", "func"),
    ("intelligence.smart_answer_reader.summarizer", "get_summarizer", "func"),
    ("intelligence.smart_answer_reader.tts_preparer", "get_tts_preparer", "func"),
    ("intelligence.verification.action_verifier", "get_action_verifier", "func"),
    ("intelligence.verification.file_verifier", "get_file_verifier", "func"),
    ("intelligence.verification.result_verifier", "get_result_verifier", "func"),
    ("intelligence.verification.screenshot_verifier", "get_screenshot_verifier", "func"),
    ("intelligence.verification.success_evaluator", "get_success_evaluator", "func"),
    ("intelligence.verification.verification_engine", "get_verification_engine", "func"),
    ("intelligence.world_state.active_context", "get_active_context", "func"),
    ("intelligence.world_state.context_snapshot", "get_context_snapshot", "func"),
    ("intelligence.world_state.device_state", "get_device_state", "func"),
    ("intelligence.world_state.environment_state", "get_environment_state", "func"),
    ("intelligence.world_state.pc_state", "get_pc_state", "func"),
    ("intelligence.world_state.task_state", "get_task_state", "func"),
    ("intelligence.world_state.world_state_manager", "get_world_state_manager", "func"),
    ("learn.from_feedback", "get_from_feedback", "func"),
    ("learn.from_habit", "get_from_habit", "func"),
    ("learn.improve_self", "get_improve_self", "func"),
    ("learning.experience", "get_experience_store", "func"),
    ("learning.forgetting", "get_forgetting", "func"),
    ("learning.learner", "get_learner", "func"),
    ("learning.learning_scheduler", "get_learning_scheduler", "func"),
    ("learning.memory_consolidator", "get_memory_consolidator", "func"),
    ("learning.skill_learner", "get_skill_learner", "func"),
    ("monitoring.alerts", "get_alert_manager", "func"),
    ("monitoring.performance", "get_performance_tracker", "func"),
    ("perception.voice_processor", "get_voice_processor", "func"),
    ("predict.mood_predict", "get_mood_predict", "func"),
    ("predict.need_before", "get_need_before", "func"),
    ("predict.next_action", "get_next_action", "func"),
    ("proactive.engine", "get_proactive_engine", "func"),
    ("proactive.triggers.event_driven", "get_event_driven_triggers", "func"),
    ("proactive.triggers.time_based", "get_time_based_triggers", "func"),
    ("ui.voice_ui.avatar.bridge", "get_avatar_controller", "func"),
    ("voice.stt.google_stt", "get_google_stt", "func"),
    ("voice_intelligence.custom_tts_engine", "get_custom_tts", "func"),
    ("voice_intelligence.emotion_analyzer", "get_emotion_analyzer", "func"),
    ("voice_intelligence.offline_voice_pipeline", "get_offline_pipeline", "func"),
    ("voice_intelligence.speaker_diarization", "get_diarizer", "func"),
    ("learning.knowledge_extractor", "KnowledgeExtractor", "class"),
    ("learning_engine.mistake_learner", "MistakeLearner", "class"),
    ("learning_engine.reinforcement_learner", "ReinforcementLearner", "class"),
    ("memory.vector_db.__init__", "get_vector_store", "func"),
    ("memory.vector_db.chroma_client", "ChromaVectorStore", "class"),
    ("memory.vector_db.faiss_client", "FaissVectorStore", "class"),
    ("models.whisper.loader", "WhisperTranscriber", "class"),
    ("multi_agent_swarm.specialist_agents.base_specialist", "BaseSpecialistAgent", "class"),
    ("multi_agent_swarm.specialist_agents.code_agent", "SwarmCodeAgent", "class"),
    ("multi_agent_swarm.specialist_agents.data_analyst_agent", "SwarmDataAnalystAgent", "class"),
    ("multi_agent_swarm.specialist_agents.devops_agent", "SwarmDevOpsAgent", "class"),
    ("multi_agent_swarm.specialist_agents.research_agent", "SwarmResearchAgent", "class"),
    ("multi_agent_swarm.specialist_agents.security_agent", "SwarmSecurityAgent", "class"),
    ("multi_agent_swarm.specialist_agents.writer_agent", "SwarmWriterAgent", "class"),
    ("stability.resource_cleanup", "ResourceRegistry", "class"),
    ("ui.bridge", "get_health", "func"),
    ("ui.mobile.api.routes", "create_app", "func"),
    ("ui.overlay.overlay", "Overlay", "class"),
    ("ui.voice_ui.avatar.states", "AvatarController", "class"),
    ("ui.web_ui.app", "create_app", "func"),
    ("utils.timers", "Timer", "class"),
]


UNSAFE_MODULES = [
    ("actions.click_mouse", "get_click_mouse", "func"),
    ("actions.fill_form", "get_fill_form", "func"),
    ("actions.open_app", "get_open_app", "func"),
    ("actions.send_message", "get_send_message", "func"),
    ("actions.type_text", "get_type_text", "func"),
    ("ai.cloud_models.deepseek_client", "get_deepseek_client", "func"),
    ("ai.cloud_models.gemini_client", "get_gemini_client", "func"),
    ("ai.cloud_models.nvidia_client", "get_nvidia_client", "func"),
    ("ai.cloud_models.openrouter_client", "get_openrouter_client", "func"),
    ("ai.cloud_models.xkiro_client", "get_xkiro_client", "func"),
    ("ai.llm.model_factory", "get_model_factory", "func"),
    ("ai.prompt_manager", "get_prompt_manager", "func"),
    ("ai.router", "get_client", "func"),
    ("connect.email", "get_email", "func"),
    ("connect.spotify", "get_spotify", "func"),
    ("connect.whatsapp", "get_whatsapp", "func"),
    ("connect.youtube", "get_youtube", "func"),
    ("core.autonomous_engine", "get_autonomous_engine", "func"),
    ("core.brain_p18", "get_brain", "func"),
    ("core.response_manager", "get_response_manager", "func"),
    ("execution.app_launcher", "get_app_launcher", "func"),
    ("execution.auto_player", "get_auto_player", "func"),
    ("execution.macro_executor", "get_macro_executor", "func"),
    ("execution.self_healer", "get_self_healer", "func"),
    ("execution.web_automator", "get_web_automator", "func"),
    ("home.ac_control", "get_ac_control", "func"),
    ("home.camera_guard", "get_camera_guard", "func"),
    ("home.light_control", "get_light_control", "func"),
    ("home.routine", "get_routine", "func"),
    ("integration.error_hardening", "get_hardened_handler", "func"),
    ("mouth.auto_reply", "get_auto_reply", "func"),
    ("mouth.ultron_voice", "get_ultron_voice", "func"),
    ("mouth.silent_mode", "get_silent_mode", "func"),
    ("mouth.whisper_talk", "get_whisper_talk", "func"),
    ("safety.action_approval", "get_action_approval_gate", "func"),
    ("safety.guardian", "get_learning_guardian", "func"),
    ("safety.learning_policy", "get_learning_policy", "func"),
    ("safety.policy", "get_safety_policy", "func"),
    ("safety.review_queue", "get_review_queue", "func"),
    ("safety.sandbox", "get_sandbox_executor", "func"),
    ("safety.trust_policy", "get_trust_policy", "func"),
    ("search.people_search", "get_people_search", "func"),
    ("search.price_search", "get_price_search", "func"),
    ("security.authentication", "get_auth_manager", "func"),
    ("security.data_vault", "get_data_vault", "func"),
    ("security.privacy_shield", "get_privacy_shield", "func"),
    ("security.vault", "get_vault", "func"),
    ("security.voice_lock", "get_voice_lock", "func"),
    ("skills.versions", "get_skill_versions", "func"),
    ("agents.assistant_agent", "AssistantAgent", "class"),
    ("ai.few_shot_learning", "FewShotLearner", "class"),
    ("ai.llm.gemini_client", "GeminiLLMClient", "class"),
    ("ai.llm.groq_client", "GroqLLMClient", "class"),
    ("ai.llm.huggingface_client", "HuggingFaceLLMClient", "class"),
    ("ai.llm.ollama_client", "OllamaLLMClient", "class"),
    ("apps.base_app", "BaseApp", "class"),
    ("apps.browsers.brave", "BraveApp", "class"),
    ("apps.browsers.chrome", "ChromeApp", "class"),
    ("apps.browsers.edge", "EdgeApp", "class"),
    ("apps.browsers.firefox", "FirefoxApp", "class"),
    ("apps.browsers.opera", "OperaApp", "class"),
    ("apps.cloud._sync_folder_base", "SyncFolderApp", "class"),
    ("apps.cloud.google_drive", "GoogleDriveApp", "class"),
    ("apps.communication.discord", "DiscordApp", "class"),
    ("apps.communication.messenger", "MessengerApp", "class"),
    ("apps.communication.signal", "SignalApp", "class"),
    ("apps.communication.skype", "SkypeApp", "class"),
    ("apps.communication.slack", "SlackApp", "class"),
    ("apps.communication.telegram", "TelegramApp", "class"),
    ("apps.communication.whatsapp", "WhatsAppApp", "class"),
    ("apps.design.canva", "CanvaApp", "class"),
    ("apps.design.figma", "FigmaApp", "class"),
    ("apps.design.gimp", "GimpApp", "class"),
    ("apps.design.illustrator", "IllustratorApp", "class"),
    ("apps.design.photoshop", "PhotoshopApp", "class"),
    ("apps.development.docker", "DockerApp", "class"),
    ("apps.development.git", "GitApp", "class"),
    ("apps.development.postman", "PostmanApp", "class"),
    ("apps.development.pycharm", "PyCharmApp", "class"),
    ("apps.development.terminal", "TerminalApp", "class"),
    ("apps.development.vscode", "VSCodeApp", "class"),
    ("apps.gaming.discord_gaming", "DiscordGamingApp", "class"),
    ("apps.gaming.epic_games", "EpicGamesApp", "class"),
    ("apps.gaming.steam", "SteamApp", "class"),
    ("apps.gaming.xbox", "XboxApp", "class"),
    ("apps.media.itunes", "ITunesApp", "class"),
    ("apps.media.spotify", "SpotifyApp", "class"),
    ("apps.media.vlc", "VLCApp", "class"),
    ("apps.media.windows_media", "WindowsMediaApp", "class"),
    ("apps.media.youtube_music", "YouTubeMusicApp", "class"),
    ("apps.office.access", "AccessApp", "class"),
    ("apps.office.excel", "ExcelApp", "class"),
    ("apps.office.onenote", "OneNoteApp", "class"),
    ("apps.office.outlook", "OutlookApp", "class"),
    ("apps.office.powerpoint", "PowerPointApp", "class"),
    ("apps.office.teams", "TeamsApp", "class"),
    ("apps.office.word", "WordApp", "class"),
    ("apps.security.antivirus", "AntivirusApp", "class"),
    ("apps.security.bitlocker", "BitLockerApp", "class"),
    ("apps.security.firewall", "FirewallApp", "class"),
    ("apps.security.windows_defender", "WindowsDefenderApp", "class"),
    ("apps.system.control_panel", "ControlPanelApp", "class"),
    ("apps.system.device_manager", "DeviceManagerApp", "class"),
    ("apps.system.file_explorer", "FileExplorerApp", "class"),
    ("apps.system.powershell", "PowerShellApp", "class"),
    ("apps.system.registry", "RegistryApp", "class"),
    ("apps.system.settings", "SettingsApp", "class"),
    ("apps.system.task_manager", "TaskManagerApp", "class"),
    ("apps.utilities.calculator", "CalculatorApp", "class"),
    ("apps.utilities.notepad", "NotepadApp", "class"),
    ("apps.utilities.paint", "PaintApp", "class"),
    ("apps.utilities.pdf_reader", "PDFReaderApp", "class"),
    ("apps.utilities.snipping_tool", "SnippingToolApp", "class"),
    ("apps.utilities.sticky_notes", "StickyNotesApp", "class"),
    ("apps.utilities.winrar", "WinRARApp", "class"),
    ("automation.RPA.desktop_rpa", "DesktopRPASkill", "class"),
    ("automation.RPA.web_rpa", "WebRPA", "class"),
    ("automation.__init__", "_SchedulerSkill", "class"),
    ("automation.clipboard.manager", "ClipboardManagerSkill", "class"),
    ("automation.conditions.logic_conditions", "LogicConditionsSkill", "class"),
    ("automation.keyboard.controller", "KeyboardControllerSkill", "class"),
    ("automation.macro.player", "MacroPlayerSkill", "class"),
    ("automation.macro.recorder", "MacroRecorderSkill", "class"),
    ("automation.mouse.controller", "MouseControllerSkill", "class"),
    ("automation.triggers.event_triggers", "EventTriggersSkill", "class"),
    ("automation.ui.element_finder", "ElementFinderSkill", "class"),
    ("automation.workflow.engine", "WorkflowEngine", "class"),
    ("autonomous_web.session_manager", "SessionManager", "class"),
    ("browser.automation.download_manager", "DownloadManager", "class"),
    ("browser.automation.tab_manager", "GenericTabManager", "class"),
    ("browser.chrome.bookmarks", "ChromeBookmarks", "class"),
    ("browser.chrome.cookies", "ChromeCookies", "class"),
    ("browser.chrome.downloads", "ChromeDownloads", "class"),
    ("browser.chrome.history", "ChromeHistory", "class"),
    ("browser.edge.downloads", "EdgeDownloads", "class"),
    ("browser.firefox.downloads", "FirefoxDownloads", "class"),
    ("certification.tool_inventory", "build_inventory", "func"),
    ("core.planner", "Planner", "class"),
    ("cross_device.remote_controller", "RemoteController", "class"),
    ("cross_device.universal_clipboard", "UniversalClipboard", "class"),
    ("deep_os_integration.clipboard_intelligence", "ClipboardIntelligence", "class"),
    ("deep_os_integration.driver_controller", "DriverController", "class"),
    ("deep_os_integration.global_hook_manager", "GlobalHookManager", "class"),
    ("deep_os_integration.registry_monitor", "RegistryMonitor", "class"),
    ("deep_os_integration.window_manager_hook", "WindowManagerHook", "class"),
    ("integration.base_integration", "BaseIntegration", "class"),
    ("plugins.installed.telegram.plugin", "TelegramPlugin", "class"),
    ("plugins.manager", "PluginManager", "class"),
    ("plugins.sandbox.executor", "PluginSandbox", "class"),
    ("plugins.versioning.updater", "PluginVersionManager", "class"),
    ("skills.app_control.controller", "AppController", "class"),
    ("skills.browser.automation", "BrowserAutomationSkill", "class"),
    ("skills.communication.messaging", "MessagingHandler", "class"),
    ("skills.data.processor", "DataProcessor", "class"),
    ("skills.email.handler", "EmailHandler", "class"),
    ("skills.vision.camera_skill", "VisionSkill", "class"),
    ("skills.vision.change_detection_skill", "ChangeDetectionSkill", "class"),
    ("skills.vision.object_detection_skill", "CameraObjectDetectionSkill", "class"),
    ("skills.vision.ocr_skill", "CameraOCRSkill", "class"),
    ("skills.vision.scene_skill", "CameraSceneSkill", "class"),
    ("skills.windows.manager", "WindowsManager", "class"),
    ("system_control.applications.development_control", "DevelopmentControl", "class"),
    ("system_control.hardware.camera_control", "CameraControl", "class"),
    ("system_control.hardware.cpu_control", "CPUControl", "class"),
    ("system_control.hardware.fan_control", "FanControl", "class"),
    ("system_control.hardware.gpu_control", "GPUControl", "class"),
    ("system_control.hardware.speaker_control", "SpeakerControl", "class"),
    ("system_control.hardware.microphone_control", "MicrophoneControl", "class"),
    ("system_control.hardware.keyboard_control", "KeyboardHardwareControl", "class"),
    ("system_control.hardware.mouse_control", "MouseHardwareControl", "class"),
    ("system_control.hardware.printer_manager", "PrinterManager", "class"),
    ("system_control.hardware.ram_optimizer", "RAMOptimizer", "class"),
    ("system_control.hardware.scanner_manager", "ScannerManager", "class"),
    ("system_control.hardware.touchpad_control", "TouchpadControl", "class"),
    ("system_control.hardware.usb_control", "USBControl", "class"),
]


def _load_one(dotted_module: str, entry_point: str, kind: str):
    """Import `dotted_module` and either call entry_point() (kind=
    "func", the codebase's get_<name>() singleton convention) or
    instantiate entry_point() (kind="class", zero-arg constructor).
    Returns the instance, or None if the module/dependency is missing
    or construction raised - failure is logged, never fatal."""
    try:
        mod = importlib.import_module(dotted_module)
        target = getattr(mod, entry_point)
        return target()
    except Exception as e:
        logger.info(f"[registry] skipped {dotted_module}.{entry_point} ({kind}): {e}")
        return None


def wire_all_modules() -> dict:
    """Wire every safe module (always, unless explicitly disabled) and
    every unsafe module (only if ULTRON_UNSAFE_MODULES_ENABLED=true).

    Returns {"safe": {name: instance_or_None}, "unsafe": {...}} so the
    caller (core/assistant.py) can attach live instances wherever it
    needs them, and so callers can see at a glance what actually came
    up vs what was skipped (missing deps, disabled flag, load error).
    """
    result = {"safe": {}, "unsafe": {}}

    safe_on = _flag("ULTRON_SAFE_MODULES_ENABLED", "true")
    unsafe_on = _flag("ULTRON_UNSAFE_MODULES_ENABLED", "false")

    if safe_on:
        for dotted, entry, kind in SAFE_MODULES:
            short = dotted.split(".")[-1]
            result["safe"][short] = _load_one(dotted, entry, kind)
        loaded = sum(1 for v in result["safe"].values() if v is not None)
        logger.info(f"[registry] SAFE modules: {loaded}/{len(SAFE_MODULES)} wired")
    else:
        logger.info("[registry] SAFE modules OFF (ULTRON_SAFE_MODULES_ENABLED=false)")

    if unsafe_on:
        for dotted, entry, kind in UNSAFE_MODULES:
            short = dotted.split(".")[-1]
            result["unsafe"][short] = _load_one(dotted, entry, kind)
        loaded = sum(1 for v in result["unsafe"].values() if v is not None)
        logger.info(
            f"[registry] UNSAFE modules: {loaded}/{len(UNSAFE_MODULES)} wired "
            f"(ULTRON_UNSAFE_MODULES_ENABLED=true - full system-control trust granted)"
        )
    else:
        logger.info(
            f"[registry] UNSAFE modules OFF ({len(UNSAFE_MODULES)} modules skipped - "
            f"set ULTRON_UNSAFE_MODULES_ENABLED=true in .env to enable shell/registry/"
            f"network/credential-capable modules)"
        )

    return result
