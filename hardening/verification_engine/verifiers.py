"""
Verifiers
=========
Ten domain verifiers (System / App / Browser / File / Keyboard-Mouse /
Media / Voice-TTS / Memory / Automation / Integration), a DefaultVerifier
fallback for anything that doesn't match one of the ten, and
route_verifier() - the keyword-based dispatch between a tool name and the
verifier that should judge it.

Every verifier shares one generic baseline (_generic_outcome) built purely
from result_normalizer.NormalizedResult's success/error/data fields, then
layers a handful of concrete, previously-real-bug-shaped checks on top
where this codebase's own history (see /areas/ultron-assistant.md's phase
log) shows generic success/error checking isn't enough - e.g. a
confirm-gated destructive action that reports success without the confirm
flag ever being set, or youtube_play only opening a search page instead of
actually starting playback (both patterns this project has hit for real).
Routing is keyword/substring based rather than an exhaustive tool list, on
purpose - it degrades to DefaultVerifier for new tools nobody has taught
this module about yet, instead of raising or silently mis-classifying.
"""

from __future__ import annotations

from typing import Optional

from ..result_states import ResultState
from .base import BaseVerifier, VerifierOutcome


def _generic_outcome(evidence) -> VerifierOutcome:
    r = evidence.result
    if r.error:
        return VerifierOutcome(ResultState.VERIFIED_FAILURE, f"tool reported an error: {r.error}", confidence=0.9)
    if r.success is True:
        if r.data:
            return VerifierOutcome(
                ResultState.VERIFIED_SUCCESS, "success=True with result data to back it up", confidence=0.7
            )
        return VerifierOutcome(
            ResultState.VERIFIED_SUCCESS, "success=True (no result data to cross-check further)", confidence=0.5
        )
    if r.success is False:
        return VerifierOutcome(ResultState.VERIFIED_FAILURE, "tool reported success=False", confidence=0.8)
    # success is None - no explicit signal either way from the tool itself.
    if r.data:
        return VerifierOutcome(
            ResultState.PARTIAL_SUCCESS, "result data returned but no explicit success/error signal", confidence=0.3
        )
    return VerifierOutcome(
        ResultState.UNKNOWN, "no success/error signal and no result data to infer from", confidence=0.2
    )


class SystemVerifier(BaseVerifier):
    """Power state, brightness/volume-as-system-setting, process/service
    inspection, CPU/RAM, disk, firewall/defender, accessibility toggles."""

    name = "system"

    _CONFIRM_GATED = {"shutdown_pc", "restart_pc", "sign_out", "kill_process", "call_phone"}
    _NUMERIC_EXPECTED = {
        "get_cpu_ram_usage": ("cpu", "ram"),
        "get_battery_status": ("percent", "battery"),
        "get_disk_usage": ("free", "total", "used", "percent"),
    }

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        # Confirm-gated destructive actions: real prior bug shape in this
        # codebase (ULTRON's shutdown/restart/kill tools take a `confirm`
        # flag precisely so the model can't trigger them by accident) - a
        # success report with confirm never actually set to True means the
        # action was correctly skipped, not that it happened.
        if tool in self._CONFIRM_GATED and evidence.arguments.get("confirm") is not True:
            if outcome.state == ResultState.VERIFIED_SUCCESS:
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"{tool} called without confirm=True - the destructive action was (correctly) not taken, "
                    "even though the tool call itself didn't error",
                    confidence=0.6,
                )
            return outcome

        # call_phone's own docstring is explicit that success only means
        # the tel: handoff to the OS succeeded, not that a call actually
        # connected - webbrowser.open() can't see past its own OS call.
        # Same "don't let a bare success=True mask an unverifiable
        # side-effect" stance as youtube_play below, since there's no
        # stronger signal available to check against here.
        if tool == "call_phone" and outcome.state == ResultState.VERIFIED_SUCCESS:
            return VerifierOutcome(
                ResultState.PARTIAL_SUCCESS,
                "call_phone reported success but that only confirms the tel: handoff to the OS succeeded, "
                "not that a call actually connected",
                confidence=0.5,
            )

        expected_fields = self._NUMERIC_EXPECTED.get(tool)
        if expected_fields and outcome.state == ResultState.VERIFIED_SUCCESS:
            data_str = " ".join(str(k).lower() for k in evidence.result.data.keys())
            if not any(f in data_str for f in expected_fields):
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"{tool} reported success but result data doesn't contain any of the expected fields {expected_fields} - "
                    "can't confirm the numbers themselves are real",
                    confidence=0.4,
                )

        return outcome


class AppVerifier(BaseVerifier):
    """Launching/closing/focusing apps and windows, and the dedicated
    per-app automations (apps/communication, apps/media, ...) - e.g.
    whatsapp_send_message, spotify_search_and_play."""

    name = "app"

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        # Prior real bug in this project: WhatsApp/Telegram/etc. messages
        # got typed into the UI but the send step was never actually
        # triggered, while the tool still reported success. Where a
        # "send_message"-shaped tool's own result data mentions the message
        # was only typed/entered (not sent), don't let a bare success=True
        # mask that.
        if "send_message" in tool or tool.endswith("_send"):
            data_str = " ".join(str(v).lower() for v in evidence.result.data.values())
            if outcome.state == ResultState.VERIFIED_SUCCESS and "typed" in data_str and "sent" not in data_str:
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"{tool} reported success but result data mentions the message was typed, not confirmed sent",
                    confidence=0.4,
                )

        if tool in ("open_application", "close_application") and not evidence.arguments.get("app_name"):
            return VerifierOutcome(
                ResultState.UNKNOWN,
                f"{tool} called with no app_name to verify against",
                confidence=0.2,
            )

        return outcome


class BrowserVerifier(BaseVerifier):
    """Chrome/browser automation, URLs and tabs, bookmarks, browsing
    history, YouTube playback."""

    name = "browser"

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        # Prior real bug in this project: youtube_search only ever opened
        # the search-results page and never actually played anything, while
        # still reporting success. youtube_play is the fixed tool, but if a
        # future regression brings that pattern back (or a call site still
        # uses youtube_search expecting playback), the result data itself
        # is the only place this is still detectable.
        if tool in ("youtube_play", "youtube_search") and outcome.state == ResultState.VERIFIED_SUCCESS:
            data_str = " ".join(str(v).lower() for v in evidence.result.data.values())
            if "results" in data_str and "watch" not in data_str and "play" not in data_str:
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"{tool} reported success but result data only mentions a search-results page, not a playing video",
                    confidence=0.4,
                )

        if tool in ("open_url", "chrome_navigate") and not (
            evidence.arguments.get("url") or evidence.arguments.get("action")
        ):
            return VerifierOutcome(
                ResultState.UNKNOWN,
                f"{tool} called with no url/action to verify the navigation against",
                confidence=0.2,
            )

        return outcome


class FileVerifier(BaseVerifier):
    """Filesystem operations, PDF/Office document handling, archives,
    clipboard, screenshots."""

    name = "file"

    _PATH_ARG_TOOLS = {
        "create_file": "file_path",
        "write_file": "file_path",
        "delete_file": "file_path",
        "copy_file": "destination",
        "move_file": "destination",
        "create_folder": "folder_path",
        "delete_folder": "folder_path",
    }

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        path_arg = self._PATH_ARG_TOOLS.get(tool)
        if path_arg and not evidence.arguments.get(path_arg):
            return VerifierOutcome(
                ResultState.UNKNOWN,
                f"{tool} called with no {path_arg} to verify the operation against",
                confidence=0.2,
            )

        return outcome


class KeyboardMouseVerifier(BaseVerifier):
    """Raw input primitives - typing into whatever has focus, key/hotkey
    presses, mouse move/click/scroll, clipboard read/write, and macro
    recording of the same. Deliberately separate from AppVerifier: these
    tools have no idea *what* they typed into or clicked on - they just
    report that an input event was dispatched - so the bar for what
    success=True can actually promise is lower here than for a
    UI-element-aware tool like click_ui_element."""

    name = "keyboard_mouse"

    _COORD_TOOLS = {"mouse_move": ("x", "y"), "mouse_click": ("x", "y")}

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        # type_text / press_key report success once the OS-level input
        # event was dispatched - they can't confirm which field (if any)
        # actually received it, since that depends on window focus at the
        # moment the call ran, which this layer has no independent way to
        # check. Never claim more than "the keystroke was sent".
        if tool in ("type_text", "press_key") and outcome.state == ResultState.VERIFIED_SUCCESS:
            return VerifierOutcome(
                ResultState.PARTIAL_SUCCESS,
                f"{tool} reported success=True, but this only confirms the input event was dispatched - "
                "not that the intended window/field had focus to receive it",
                confidence=0.4,
            )

        # mouse_move/mouse_click without explicit coordinates just acts on
        # the current cursor position - not wrong, but nothing here can
        # verify *what* got clicked.
        coords = self._COORD_TOOLS.get(tool)
        if coords and not all(evidence.arguments.get(c) is not None for c in coords):
            return VerifierOutcome(
                ResultState.PARTIAL_SUCCESS,
                f"{tool} called with no explicit {coords} - acted on current cursor position, "
                "which this layer can't verify was over the intended target",
                confidence=0.3,
            )

        return outcome


class MediaVerifier(BaseVerifier):
    """Media playback controls, system volume/mute, and the movie
    assistant (mood -> suggestion -> availability -> play)."""

    name = "media"

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        if tool in ("play_movie", "recommend_and_play_movie") and outcome.state == ResultState.VERIFIED_SUCCESS:
            data_str = " ".join(str(v).lower() for v in evidence.result.data.values())
            if "trailer" in data_str and "fallback" in data_str:
                # modules/movie_assistant/auto_player.py's documented
                # graceful-degradation path (falls back to a trailer when
                # the real platform isn't reachable) - real, but weaker
                # than what "play the movie" implies.
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"{tool} fell back to trailer playback rather than the movie itself",
                    confidence=0.4,
                )

        return outcome


class VoiceTTSVerifier(BaseVerifier):
    """Text-to-speech engine/backend switching, voice-command shortcuts,
    and speaker enrollment/identification off a mic recording. Split out
    of MediaVerifier because these tools' failure modes are about
    identity/configuration ("did it actually switch engines", "did it
    recognize the right speaker"), not playback state."""

    name = "voice_tts"

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        # set_tts_engine reporting success but echoing back a different
        # engine than what was requested means the switch didn't actually
        # take - a real "claimed vs actual" mismatch shape, same family as
        # the youtube_play/send_message regressions BrowserVerifier and
        # AppVerifier guard against.
        if tool == "set_tts_engine" and outcome.state == ResultState.VERIFIED_SUCCESS:
            requested = evidence.arguments.get("engine")
            data_str = " ".join(str(v).lower() for v in evidence.result.data.values())
            if requested and str(requested).lower() not in data_str:
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"set_tts_engine reported success but result data doesn't confirm engine={requested} took effect",
                    confidence=0.4,
                )

        # identify_speaker_from_mic recording a clip and reporting success
        # doesn't by itself mean a known speaker was matched - "recorded
        # fine, nobody enrolled matched" is a real, different outcome than
        # "identified Sir with high confidence" and a bare success=True
        # can't be trusted to tell them apart.
        if tool == "identify_speaker_from_mic" and outcome.state == ResultState.VERIFIED_SUCCESS:
            data_str = " ".join(str(v).lower() for v in evidence.result.data.values())
            if "no match" in data_str or "unknown" in data_str or "unrecognized" in data_str:
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    "identify_speaker_from_mic reported success but result data indicates no enrolled speaker matched",
                    confidence=0.4,
                )

        return outcome


class MemoryVerifier(BaseVerifier):
    """Notes, todos, calendar, health/mood logging, episodic/semantic
    recall, RAG answers, fact-checking."""

    name = "memory"

    def verify(self, evidence) -> VerifierOutcome:
        return _generic_outcome(evidence)


class AutomationVerifier(BaseVerifier):
    """RPA record/play/edit, triggers (file/time/system), conditions and
    loops, and the vision-based screen/form/diagram parsing tools that
    automation chains often lean on."""

    name = "automation"

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        if tool == "rpa_play" and not evidence.arguments.get("script_name"):
            return VerifierOutcome(
                ResultState.UNKNOWN,
                "rpa_play called with no script_name to verify which script actually ran",
                confidence=0.2,
            )

        return outcome


class IntegrationVerifier(BaseVerifier):
    """Cross-service/third-party integrations that leave this machine
    entirely - raw networking clients (SSH/FTP/HTTP/WebSocket), outgoing
    webhooks (Discord/Teams), and external-API-backed lookups (e.g.
    weather). Split out from SystemVerifier/MemoryVerifier because a
    success here depends on a remote endpoint's behavior, not just this
    process's - which means "no error surfaced" is weaker evidence than
    it is for a purely local tool."""

    name = "integration"

    _STATUS_TOOLS = {"http_request", "ssh_run_command", "ssh_command"}

    def verify(self, evidence) -> VerifierOutcome:
        outcome = _generic_outcome(evidence)
        tool = evidence.tool_name

        # An HTTP/SSH call can report success=True purely because the
        # local client didn't raise (connection opened, bytes sent) while
        # the remote side answered with an error status/stderr embedded in
        # the response body - a network client's own success flag usually
        # only means "the round trip completed", not "the remote endpoint
        # was happy with it".
        if tool in self._STATUS_TOOLS and outcome.state == ResultState.VERIFIED_SUCCESS:
            data_str = " ".join(str(v).lower() for v in evidence.result.data.values())
            if any(
                sig in data_str for sig in ("500", "502", "503", "timeout", "refused", "unauthorized", "403", "404")
            ):
                return VerifierOutcome(
                    ResultState.PARTIAL_SUCCESS,
                    f"{tool} reported success but result data contains a remote error/status signal - "
                    "the round trip completed, the remote endpoint may not have",
                    confidence=0.4,
                )

        if "webhook" in tool and outcome.state == ResultState.VERIFIED_SUCCESS and not evidence.result.data:
            return VerifierOutcome(
                ResultState.PARTIAL_SUCCESS,
                f"{tool} reported success=True with no response data to confirm the remote service accepted it",
                confidence=0.35,
            )

        return outcome


class DefaultVerifier(BaseVerifier):
    """Fallback for any tool name that doesn't match one of the ten
    categories above - new tools, or anything this module simply hasn't
    been taught about yet. Generic success/error/data reasoning only, by
    design: guessing at domain-specific rules for a tool this module
    doesn't recognize would be worse than admitting it doesn't know."""

    name = "default"

    def verify(self, evidence) -> VerifierOutcome:
        return _generic_outcome(evidence)


_SYSTEM = SystemVerifier()
_APP = AppVerifier()
_BROWSER = BrowserVerifier()
_FILE = FileVerifier()
_KEYBOARD_MOUSE = KeyboardMouseVerifier()
_MEDIA = MediaVerifier()
_VOICE_TTS = VoiceTTSVerifier()
_MEMORY = MemoryVerifier()
_AUTOMATION = AutomationVerifier()
_INTEGRATION = IntegrationVerifier()
_DEFAULT = DefaultVerifier()

# Ordered (category_keywords, verifier) - first substring match against the
# tool name wins. Order matters where a tool name could plausibly match
# more than one bucket (e.g. "media_volume_down" vs a bare "volume" system
# keyword) - more specific/media-ish keywords are listed ahead of the
# broader system ones they'd otherwise be shadowed by.
_ROUTES: list = [
    # Voice/TTS ahead of Media - kept as its own explicit block so a future
    # media keyword can't accidentally shadow it.
    (
        [
            "set_tts_engine",
            "list_voice_engines",
            "add_voice_command",
            "remove_voice_command",
            "list_voice_commands",
            "enroll_speaker_voice",
            "identify_speaker_from_mic",
            "list_enrolled_speakers",
            "forget_speaker",
            "detect_voice_emotion",
        ],
        _VOICE_TTS,
    ),
    (
        [
            "media_",
            "spotify",
            "vlc_",
            "itunes_",
            "windows_media",
            "analyze_mood",
            "suggest_movie",
            "check_movie_availability",
            "play_movie",
            "recommend_and_play_movie",
        ],
        _MEDIA,
    ),
    # Raw input primitives ahead of Automation/App so e.g. "mouse_click"
    # isn't shadowed by a broader keyword elsewhere.
    (
        [
            "type_text",
            "press_key",
            "mouse_move",
            "mouse_click",
            "mouse_scroll",
            "start_macro_recording",
            "stop_macro_recording",
            "play_macro",
        ],
        _KEYBOARD_MOUSE,
    ),
    # External/networked third-party services ahead of App - "webhook" is a
    # more specific signal than the "discord_"/"teams_"/etc. app-integration
    # prefixes below, which otherwise shadow it (discord_send_webhook_message
    # would match "discord_" in the App route first).
    (
        [
            "ssh_",
            "ftp_",
            "http_request",
            "websocket_",
            "webhook",
            "weather_",
            "get_weather",
            "linkedin_",
            "twitter_",
            "google_drive_",
            # Task 7's webhook fan-out (Slack/Discord/Zapier) - same
            # leaves-the-machine, remote-endpoint-dependent shape as the
            # webhook keyword above.
            "post_to_social",
        ],
        _INTEGRATION,
    ),
    (
        [
            "chrome_",
            "open_url",
            "youtube_search",
            "youtube_",
            "scroll_chrome",
            "type_in_chrome",
            "bookmark",
            "browser_history",
            "browsing_activity",
            "browser",
            "list_all_tabs",
            "close_tab",
            "close_tabs_matching",
            "fill_form",
            "submit_form",
            "save_form_profile",
            "autofill_form",
            "read_url",
            "search_internet",
            # Non-Chrome browsers + shared tab/download-history variants (same
            # shape of automation as the chrome_ tools above, different browser).
            "brave_",
            "edge_",
            "firefox_",
            "opera_",
            "gtab_",
            "scroll_edge",
            "scroll_firefox",
            "type_in_edge",
            "close_edge_tab",
            "close_firefox_tab",
            "list_edge_tabs",
            "list_firefox_tabs",
            "most_visited_sites",
            "top_browsed_domains",
            "click_web_element",
            "fill_web_form",
            "extract_rendered_page",
            "scrape_",
        ],
        _BROWSER,
    ),
    (
        [
            "whatsapp_",
            "telegram_",
            "messenger_",
            "signal_",
            "skype_",
            "slack_",
            "discord_",
            "open_application",
            "close_application",
            "list_running_apps",
            "activate_window",
            "minimize_window",
            "maximize_window",
            "restore_window",
            "close_window",
            "bring_window_to_front",
            "tile_windows",
            "virtual_desktop",
            "click_ui_element",
            "type_into_ui_element",
            "list_ui_elements",
            # Same app-lifecycle/window-management domain as the block above,
            # different naming convention used by the Phase 6/29 app tools
            # (app_open/minimize_app/etc. instead of open_application/
            # minimize_window/etc.) plus specific desktop apps whose own content
            # isn't document data (creative tools, games, Paint) so App fits
            # better than File for them.
            "app_open",
            "app_close",
            "app_focus",
            "app_status",
            "app_is_running",
            "find_app",
            "list_available_apps",
            "list_apps_by_category",
            "focus_app",
            "minimize_app",
            "maximize_app",
            "restart_app",
            "kill_unresponsive_apps",
            "list_background_tasks",
            "list_windows",
            "move_window",
            "resize_window",
            "snap_window",
            "get_window_geometry",
            "close_all_by_category",
            "notepad_",
            "canva_",
            "figma_",
            "illustrator_",
            "photoshop_",
            "gimp_",
            "paint_new_canvas",
            "paint_open_file",
            "steam_",
            "epic_games_",
            "xbox_",
        ],
        _APP,
    ),
    (
        [
            "list_directory",
            "find_folder",
            "search_files",
            "read_file",
            "get_file_info",
            "create_folder",
            "create_file",
            "write_file",
            "copy_file",
            "move_file",
            "delete_file",
            "delete_folder",
            "take_screenshot",
            "empty_trash",
            "_pdf",
            "pdf_",
            "read_docx",
            "create_docx",
            "read_xlsx",
            "create_xlsx",
            "compress_files",
            "extract_archive",
            "clipboard",
            # Office document tools (word_/excel_/powerpoint_) - same "operate on
            # a document" shape as read_docx/read_xlsx above, just the Phase 29
            # per-app naming instead. CSV/JSON are also structured-data-in-a-file
            # tools, same domain. winrar_/snipping_tool_/file_explorer_/
            # download_mgr_ are all still "do something to a file on disk".
            # "word_" is spelled out as exact tool names, not a bare prefix -
            # a bare "word_" would also match "check_pass**word_**strength"
            # (System bucket, unrelated to the Word app) since routing is
            # plain substring matching, not anchored to the start of the name.
            "word_close_document",
            "word_new_document",
            "word_open_file",
            "word_print_document",
            "word_save",
            "excel_",
            "powerpoint_",
            "add_excel_formula",
            "aggregate_excel_column",
            "append_excel_rows",
            "create_excel_workbook",
            "filter_excel_rows",
            "list_excel_sheets",
            "read_excel_sheet",
            "csv_",
            "read_csv_file",
            "write_csv_file",
            "sort_csv_rows",
            "filter_csv_rows",
            "append_csv_rows",
            "aggregate_csv_column",
            "read_json_file",
            "write_json_file",
            "merge_json_file",
            "query_json_list",
            "get_json_path",
            "set_json_path",
            "winrar_",
            "audit_file_permissions",
            "reveal_file_in_explorer",
            "open_explorer_at",
            "open_file",
            "file_explorer_",
            "download_mgr_",
            "get_download_history",
            "list_downloads",
            "open_download",
            "snipping_tool_",
        ],
        _FILE,
    ),
    (
        [
            "rpa_",
            "watch_file",
            "stop_watching_file",
            "list_file_watches",
            "trigger",
            "evaluate_condition",
            "run_if_condition",
            "loop_",
            "describe_screen",
            "describe_screen_regions",
            "detect_form_fields",
            "parse_diagram",
            "read_handwriting",
            "locate_on_screen",
            "click_by_vision",
            # Screen-vision tools under a different name, plus workflow/macro/
            # plugin management - same "orchestrate a sequence of other tools"
            # domain as rpa_/trigger/loop_ above.
            "detect_faces_on_screen",
            "detect_objects_on_screen",
            "read_screen_text",
            "find_ui_text_regions",
            "list_advanced_workflows",
            "run_advanced_workflow",
            "save_advanced_workflow",
            "run_workflow",
            "save_workflow",
            "list_workflows",
            "list_macros",
            "get_task_status",
            "install_plugin",
            "list_available_plugins",
            "on_battery_threshold",
        ],
        _AUTOMATION,
    ),
    (
        [
            "save_note",
            "read_notes",
            "record_event",
            "recall_",
            "define_concept",
            "log_mood",
            "get_mood_trend",
            "calendar_event",
            "todo",
            "log_water",
            "log_sleep",
            "log_exercise",
            "health_daily_summary",
            "rag_answer",
            "reason_deeply",
            "get_api_usage",
            "fact_check_claim",
            "send_email",
            "read_inbox",
            "search_emails",
            # Other notes/knowledge apps (Notion/Obsidian/OneNote/Sticky Notes),
            # recall/fact-store variants, other mail/calendar/messaging surfaces
            # (Gmail/Outlook/gcal/SMS/mailbox), email templates, meeting
            # scheduling, and text-reasoning tools (code review, research,
            # sentiment, calculator) - all the same "read/write durable
            # information or reason over it" domain as the block above.
            "access_new_database",
            "access_open_database",
            "notion_",
            "obsidian_",
            "onenote_",
            "sticky_notes_",
            "remember_fact",
            "remember_subject_fact",
            "remember_for_search",
            "forget_fact",
            "search_facts",
            "search_memory",
            "gmail_",
            "outlook_",
            "mailbox_",
            "sms",
            "email_template",
            "gcal_",
            "cancel_meeting",
            "daily_meeting_agenda",
            "find_free_meeting_slot",
            "list_upcoming_meetings",
            "reschedule_meeting",
            "schedule_meeting",
            "explain_code",
            "fix_code",
            "review_code",
            "write_code",
            "deep_research",
            "gather_research_sources",
            "analyze_text_sentiment",
            "calculator_compute",
            # Task 7's local contacts store (same durable-record shape as
            # save_note/remember_fact above) and the real Google Calendar sync
            # (distinct from the local calendar_event/schedule_meeting tools
            # already routed here, but still a "read/write durable information"
            # tool, not a system or app action).
            "add_contact",
            "find_contact",
            "list_contacts",
            "delete_contact",
            "google_calendar_",
        ],
        _MEMORY,
    ),
    (
        [
            "shutdown_pc",
            "restart_pc",
            "sign_out",
            "cancel_shutdown",
            "sleep_now",
            "hibernate_now",
            "power_plan",
            "sleep_timeout",
            "screen_timeout",
            "battery_saver",
            "brightness",
            "volume",
            "get_cpu_ram_usage",
            "get_ip_address",
            "lock_screen",
            "get_battery_status",
            "list_processes",
            "find_process",
            "kill_process",
            "get_process_info",
            "list_services",
            "get_service_status",
            "list_startup_programs",
            "get_firewall_status",
            "get_defender_status",
            "start_defender_scan",
            "get_disk_usage",
            "toggle_narrator",
            "set_high_contrast",
            "toggle_magnifier",
            "set_sticky_keys",
            "announce",
            "show_notification",
            "get_system_info",
            "run_command",
            # OS-level security/config surfaces (antivirus, BitLocker, Defender,
            # firewall rule management, registry, Control Panel, Device Manager,
            # Settings app, Task Manager) and dev-tooling that shells out to a
            # local system process (git/docker/vscode/pycharm/postman/
            # powershell/terminal) - same "operate on this machine itself"
            # domain as shutdown_pc/kill_process/etc. above.
            "antivirus_",
            "bitlocker_",
            "windows_defender_",
            "firewall_",
            "check_password_strength",
            "generate_secure_password",
            "control_panel_",
            "device_manager_",
            "settings_",
            "task_manager_end_task",
            "registry_",
            "git_",
            "docker_",
            "vscode_",
            "pycharm_open_project",
            "postman_open_collection_link",
            "powershell_",
            "run_powershell",
            "terminal_open_here",
            "terminal_run_and_capture_command",
            # Task 7's call_phone - confirm-gated the same way shutdown_pc/
            # restart_pc/kill_process already are, so it belongs in the same
            # _CONFIRM_GATED-checked bucket rather than a new one.
            "call_phone",
        ],
        _SYSTEM,
    ),
]


def route_verifier(tool_name: Optional[str]) -> BaseVerifier:
    tool = (tool_name or "").lower()
    for keywords, verifier in _ROUTES:
        if any(kw in tool for kw in keywords):
            return verifier
    return _DEFAULT
