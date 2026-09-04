"""
New skills & integrations tool registry
========================================
Wires everything under skills/email, skills/calendar, skills/web,
skills/data, skills/communication, and integration/* into the same
tool-calling loop as every other Ultron tool - without touching the huge
existing dicts in ai/tools_schema.py, ai/tool_runtime.py, or
core/executor.py's tool_map directly (kept as small, mergeable additions
at the bottom of each instead - see the two-line imports there).

Pattern mirrors ai/tool_runtime.py's own _get_web_tools(): every client is
a lazily-instantiated module-level singleton (stateless dispatch, cheap to
share across turns/backends), and every tool handler returns the dict the
underlying skill method already produces - no extra wrapping needed since
every skill in this codebase already follows the
`{"success": True, ...}` / `{"success": False, "error": ...}` convention.

Naming: where a new tool could collide with an existing local/offline tool
(e.g. the existing `send_email`/`read_inbox` which use plain SMTP/IMAP via
agents/email_agent.py, or the existing local SQLite `add_calendar_event`),
these are prefixed by provider (`gmail_...`, `outlook_...`, `gcal_...`) so
both old and new tools stay callable side by side.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    (rather than imported) deliberately: ai/tools_schema.py imports NEW_TOOLS
    from this module at its own bottom, so importing `_tool` back from there
    would create a circular import whose success depends on which module
    happens to be imported first. This tiny pure function is cheap enough
    to just keep in sync by hand instead."""
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


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "gmail":
        from skills.email.gmail import GmailClient

        obj = GmailClient()
    elif key == "outlook_mail":
        from skills.email.outlook import OutlookClient

        obj = OutlookClient()
    elif key == "templates":
        from skills.email.templates import EmailTemplates

        obj = EmailTemplates()
    elif key == "gcal":
        from skills.calendar.google_calendar import GoogleCalendarClient

        obj = GoogleCalendarClient()
    elif key == "outlook_cal":
        from skills.calendar.outlook_calendar import OutlookCalendarClient

        obj = OutlookCalendarClient()
    elif key == "scheduler":
        from skills.calendar.scheduler import Scheduler

        obj = Scheduler()
    elif key == "scraper":
        from skills.web.scraper import WebScraper

        obj = WebScraper()
    elif key == "research":
        from skills.web.research import WebResearch

        try:
            from core.brain import get_brain

            obj = WebResearch(ai_router=get_brain())
        except Exception:
            obj = WebResearch(ai_router=None)
    elif key == "form_filler":
        from skills.web.form_filler import FormFiller

        obj = FormFiller()
    elif key == "excel_data":
        from skills.data.excel import ExcelData

        obj = ExcelData()
    elif key == "csv_data":
        from skills.data.csv import CSVData

        obj = CSVData()
    elif key == "json_data":
        from skills.data.json import JSONData

        obj = JSONData()
    elif key == "whatsapp":
        from skills.communication.whatsapp import WhatsAppClient

        obj = WhatsAppClient()
    elif key == "telegram_out":
        from skills.communication.telegram import TelegramClient

        obj = TelegramClient()
    elif key == "sms":
        from skills.communication.sms import SMSClient

        obj = SMSClient()
    elif key == "slack":
        from integration.slack.client import SlackClient

        obj = SlackClient()
    elif key == "discord":
        from integration.discord.bot import DiscordClient

        obj = DiscordClient()
    elif key == "teams":
        from integration.teams.connector import TeamsClient

        obj = TeamsClient()
    elif key == "notion":
        from integration.notion.api import NotionClient

        obj = NotionClient()
    elif key == "obsidian":
        from integration.obsidian.vault import ObsidianClient

        obj = ObsidianClient()
    elif key == "spotify":
        from integration.spotify.player import SpotifyClient

        obj = SpotifyClient()
    elif key == "youtube_data":
        from integration.youtube.controller import YouTubeClient

        obj = YouTubeClient()
    elif key == "twitter":
        from integration.twitter.poster import TwitterPoster

        obj = TwitterPoster()
    elif key == "linkedin":
        from integration.linkedin.network import LinkedInNetwork

        obj = LinkedInNetwork()
    elif key == "gmail_mailbox":
        from integration.gmail.mailbox import Mailbox

        obj = Mailbox()
    else:
        raise KeyError(f"Unknown new-skill singleton: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool handlers: name -> (raw_args_dict) -> result dict
# ---------------------------------------------------------------------------
NEW_DIRECT_HANDLERS = {
    # -- Gmail (OAuth) ----------------------------------------------------
    "gmail_send_email": lambda d: _get("gmail").send_email(
        d.get("to", ""), d.get("subject", ""), d.get("body", ""), d.get("cc"), d.get("bcc"), d.get("html", False)
    ),
    "gmail_read_emails": lambda d: _get("gmail").read_emails(
        d.get("max_results", 10), d.get("label", "INBOX"), d.get("unread_only", False)
    ),
    "gmail_search_emails": lambda d: _get("gmail").search_emails(d.get("query", ""), d.get("max_results", 10)),
    "gmail_get_email_body": lambda d: _get("gmail").get_email_body(d.get("message_id", "")),
    "gmail_mark_as_read": lambda d: _get("gmail").mark_as_read(d.get("message_id", "")),
    "gmail_delete_email": lambda d: _get("gmail").delete_email(d.get("message_id", "")),
    # -- Outlook mail (Graph) ----------------------------------------------
    "outlook_send_email": lambda d: _get("outlook_mail").send_email(
        d.get("to", ""), d.get("subject", ""), d.get("body", ""), d.get("cc"), d.get("html", False)
    ),
    "outlook_read_emails": lambda d: _get("outlook_mail").read_emails(
        d.get("max_results", 10), d.get("unread_only", False)
    ),
    "outlook_search_emails": lambda d: _get("outlook_mail").search_emails(d.get("query", ""), d.get("max_results", 10)),
    "outlook_mark_as_read": lambda d: _get("outlook_mail").mark_as_read(d.get("message_id", "")),
    "outlook_delete_email": lambda d: _get("outlook_mail").delete_email(d.get("message_id", "")),
    # -- Email templates ------------------------------------------------
    "list_email_templates": lambda d: _get("templates").list_templates(),
    "render_email_template": lambda d: _get("templates").render(d.get("name", ""), **d.get("fields", {})),
    "save_email_template": lambda d: _get("templates").save_template(
        d.get("name", ""), d.get("subject", ""), d.get("body", "")
    ),
    # -- Google Calendar --------------------------------------------------
    "gcal_create_event": lambda d: _get("gcal").create_event(
        d.get("title", ""),
        d.get("start_time", ""),
        d.get("end_time", ""),
        d.get("description", ""),
        d.get("location", ""),
        d.get("attendees"),
        d.get("timezone", "Asia/Kolkata"),
    ),
    "gcal_list_events": lambda d: _get("gcal").list_events(d.get("max_results", 10)),
    "gcal_update_event": lambda d: _get("gcal").update_event(d.get("event_id", ""), **d.get("fields", {})),
    "gcal_delete_event": lambda d: _get("gcal").delete_event(d.get("event_id", "")),
    "gcal_find_free_slots": lambda d: _get("gcal").find_free_slots(
        d.get("date", ""), d.get("duration_minutes", 30), d.get("day_start", "09:00"), d.get("day_end", "18:00")
    ),
    # -- Outlook Calendar (Graph) --------------------------------------------
    "outlook_cal_create_event": lambda d: _get("outlook_cal").create_event(
        d.get("title", ""),
        d.get("start_time", ""),
        d.get("end_time", ""),
        d.get("description", ""),
        d.get("location", ""),
        d.get("attendees"),
    ),
    "outlook_cal_list_events": lambda d: _get("outlook_cal").list_events(d.get("max_results", 10)),
    "outlook_cal_delete_event": lambda d: _get("outlook_cal").delete_event(d.get("event_id", "")),
    # -- Provider-agnostic scheduler --------------------------------------
    "schedule_meeting": lambda d: _get("scheduler").schedule_meeting(
        d.get("title", ""),
        d.get("start_time", ""),
        d.get("end_time", ""),
        d.get("description", ""),
        d.get("location", ""),
        d.get("attendees"),
    ),
    "list_upcoming_meetings": lambda d: _get("scheduler").upcoming_events(d.get("max_results", 10)),
    "cancel_meeting": lambda d: _get("scheduler").cancel_meeting(d.get("event_id", "")),
    "reschedule_meeting": lambda d: _get("scheduler").reschedule(
        d.get("event_id", ""), d.get("new_start", ""), d.get("new_end", "")
    ),
    "find_free_meeting_slot": lambda d: _get("scheduler").find_common_free_slot(
        d.get("date", ""), d.get("duration_minutes", 30)
    ),
    "daily_meeting_agenda": lambda d: _get("scheduler").daily_agenda(),
    # -- Web scraping / research --------------------------------------------
    "scrape_links": lambda d: _get("scraper").scrape_links(d.get("url", ""), d.get("same_domain_only", False)),
    "scrape_images": lambda d: _get("scraper").scrape_images(d.get("url", "")),
    "scrape_tables": lambda d: _get("scraper").scrape_tables(d.get("url", "")),
    "scrape_selector": lambda d: _get("scraper").scrape_selector(d.get("url", ""), d.get("selector", "")),
    "scrape_page_metadata": lambda d: _get("scraper").scrape_metadata(d.get("url", "")),
    "deep_research": lambda d: _get("research").research(
        d.get("query", ""), d.get("num_queries", 3), d.get("results_per_query", 3)
    ),
    # -- Form filling (Selenium) -----------------------------------------
    # fill_web_form intentionally NOT registered here - it's a duplicate
    # of the canonical, ULTRON_AUTONOMOUS_WEB_ENABLED-gated implementation
    # in ai/phase30_gated_tools.py (audit fix, item #10: two competing
    # registrations of the same tool name is a security-review risk even
    # when dict-merge order happens to make the gated one win today).
    "extract_rendered_page": lambda d: _get("form_filler").extract_after_render(
        d.get("url", ""), d.get("wait_selector")
    ),
    # -- Data: Excel / CSV / JSON --------------------------------------------
    "read_excel_sheet": lambda d: _get("excel_data").read_sheet(
        d.get("path", ""), d.get("sheet_name"), d.get("max_rows", 500)
    ),
    "create_excel_workbook": lambda d: _get("excel_data").create_workbook(
        d.get("path", ""), d.get("data", []), d.get("sheet_name", "Sheet1")
    ),
    "filter_excel_rows": lambda d: _get("excel_data").filter_rows(
        d.get("path", ""), d.get("column", ""), d.get("value")
    ),
    "aggregate_excel_column": lambda d: _get("excel_data").aggregate_column(
        d.get("path", ""), d.get("column", ""), d.get("operation", "sum")
    ),
    "read_csv_file": lambda d: _get("csv_data").read_csv(d.get("path", ""), d.get("max_rows", 1000)),
    "write_csv_file": lambda d: _get("csv_data").write_csv(d.get("path", ""), d.get("rows", [])),
    "filter_csv_rows": lambda d: _get("csv_data").filter_rows(d.get("path", ""), d.get("column", ""), d.get("value")),
    "sort_csv_rows": lambda d: _get("csv_data").sort_rows(
        d.get("path", ""), d.get("column", ""), d.get("descending", False), d.get("numeric", False)
    ),
    "aggregate_csv_column": lambda d: _get("csv_data").aggregate_column(
        d.get("path", ""), d.get("column", ""), d.get("operation", "sum")
    ),
    "read_json_file": lambda d: _get("json_data").read_json(d.get("path", "")),
    "write_json_file": lambda d: _get("json_data").write_json(d.get("path", ""), d.get("data")),
    "get_json_path": lambda d: _get("json_data").get_path(d.get("path", ""), d.get("dot_path", "")),
    "set_json_path": lambda d: _get("json_data").set_path(d.get("path", ""), d.get("dot_path", ""), d.get("value")),
    # -- Communication --------------------------------------------------
    "send_whatsapp_message": lambda d: _get("whatsapp").send_message(d.get("to", ""), d.get("message", "")),
    "send_whatsapp_template": lambda d: _get("whatsapp").send_template(
        d.get("to", ""), d.get("template_name", ""), d.get("language_code", "en_US"), d.get("params")
    ),
    "send_telegram_message": lambda d: _get("telegram_out").send_message(d.get("message", ""), d.get("chat_id")),
    "send_sms": lambda d: _get("sms").send_sms(d.get("to", ""), d.get("message", "")),
    # -- Slack ------------------------------------------------------------
    "slack_send_message": lambda d: _get("slack").send_message(
        d.get("channel", ""), d.get("text", ""), d.get("thread_ts")
    ),
    "slack_read_channel": lambda d: _get("slack").read_channel_history(d.get("channel", ""), d.get("limit", 20)),
    "slack_list_channels": lambda d: _get("slack").list_channels(d.get("limit", 100)),
    # -- Discord -----------------------------------------------------------
    "discord_send_message": lambda d: _get("discord").send_message(d.get("channel_id", ""), d.get("message", "")),
    "discord_read_channel": lambda d: _get("discord").read_channel_history(d.get("channel_id", ""), d.get("limit", 20)),
    # -- Teams -------------------------------------------------------------
    "teams_send_webhook_message": lambda d: _get("teams").send_webhook_message(
        d.get("title", ""), d.get("message", ""), d.get("webhook_url")
    ),
    "teams_send_channel_message": lambda d: _get("teams").send_channel_message(
        d.get("team_id", ""), d.get("channel_id", ""), d.get("message", "")
    ),
    # -- Notion -------------------------------------------------------------
    "notion_create_page": lambda d: _get("notion").create_page(
        d.get("parent_id", ""), d.get("title", ""), d.get("content", ""), d.get("is_database", False)
    ),
    "notion_append_text": lambda d: _get("notion").append_text(d.get("page_id", ""), d.get("text", "")),
    "notion_query_database": lambda d: _get("notion").query_database(
        d.get("database_id", ""), d.get("filter_obj"), d.get("sorts"), d.get("page_size", 20)
    ),
    "notion_search": lambda d: _get("notion").search(d.get("query", ""), d.get("filter_type")),
    # -- Obsidian ---------------------------------------------------------
    "obsidian_create_note": lambda d: _get("obsidian").create_note(
        d.get("note_path", ""), d.get("content", ""), d.get("overwrite", False)
    ),
    "obsidian_read_note": lambda d: _get("obsidian").read_note(d.get("note_path", "")),
    "obsidian_append_note": lambda d: _get("obsidian").append_note(d.get("note_path", ""), d.get("text", "")),
    "obsidian_append_daily_note": lambda d: _get("obsidian").append_to_daily_note(
        d.get("text", ""), d.get("daily_folder", "Daily")
    ),
    "obsidian_search_vault": lambda d: _get("obsidian").search_vault(d.get("query", ""), d.get("max_results", 20)),
    "obsidian_get_backlinks": lambda d: _get("obsidian").get_backlinks(d.get("note_name", "")),
    # -- Spotify -----------------------------------------------------------
    "spotify_search_track": lambda d: _get("spotify").search_track(d.get("query", ""), d.get("limit", 5)),
    "spotify_play": lambda d: _get("spotify").play(d.get("track_uri"), d.get("device_id")),
    "spotify_pause": lambda d: _get("spotify").pause(),
    "spotify_next_track": lambda d: _get("spotify").next_track(),
    "spotify_previous_track": lambda d: _get("spotify").previous_track(),
    "spotify_set_volume": lambda d: _get("spotify").set_volume(d.get("percent", 50)),
    "spotify_current_playback": lambda d: _get("spotify").current_playback(),
    # -- YouTube Data API ----------------------------------------------------
    "youtube_data_search": lambda d: _get("youtube_data").search_videos(d.get("query", ""), d.get("max_results", 5)),
    "youtube_video_details": lambda d: _get("youtube_data").get_video_details(d.get("video_id", "")),
    "youtube_channel_details": lambda d: _get("youtube_data").get_channel_details(d.get("channel_id"), d.get("handle")),
    "youtube_playlist_items": lambda d: _get("youtube_data").get_playlist_items(
        d.get("playlist_id", ""), d.get("max_results", 20)
    ),
    "youtube_video_comments": lambda d: _get("youtube_data").get_video_comments(
        d.get("video_id", ""), d.get("max_results", 10)
    ),
    # -- Round 2: remaining methods not covered in the first wiring pass ----
    "get_email_template": lambda d: _get("templates").get_template(d.get("name", "")),
    "delete_email_template": lambda d: _get("templates").delete_template(d.get("name", "")),
    "outlook_cal_update_event": lambda d: _get("outlook_cal").update_event(
        d.get("event_id", ""), **d.get("fields", {})
    ),
    "gather_research_sources": lambda d: _get("research").gather_sources(
        d.get("query", ""), d.get("num_queries", 3), d.get("results_per_query", 3), d.get("read_top_n", 3)
    ),
    "click_web_element": lambda d: _get("form_filler").click_element(
        d.get("url", ""), d.get("selector", ""), d.get("by", "css")
    ),
    "close_form_filler_browser": lambda d: _get("form_filler").close(),
    "list_excel_sheets": lambda d: _get("excel_data").list_sheets(d.get("path", "")),
    "append_excel_rows": lambda d: _get("excel_data").append_rows(
        d.get("path", ""), d.get("rows", []), d.get("sheet_name")
    ),
    "add_excel_formula": lambda d: _get("excel_data").add_formula(
        d.get("path", ""), d.get("cell", ""), d.get("formula", ""), d.get("sheet_name")
    ),
    "append_csv_rows": lambda d: _get("csv_data").append_rows(d.get("path", ""), d.get("rows", [])),
    "csv_to_json": lambda d: _get("csv_data").to_json(d.get("path", "")),
    "merge_json_file": lambda d: _get("json_data").merge_json(d.get("path", ""), d.get("updates", {})),
    "query_json_list": lambda d: _get("json_data").query_list(
        d.get("path", ""), d.get("list_dot_path", ""), d.get("filter_key", ""), d.get("filter_value")
    ),
    "send_whatsapp_media": lambda d: _get("whatsapp").send_media(
        d.get("to", ""), d.get("media_url", ""), d.get("media_type", "image"), d.get("caption", "")
    ),
    "mark_whatsapp_read": lambda d: _get("whatsapp").mark_as_read(d.get("message_id", "")),
    "send_telegram_photo": lambda d: _get("telegram_out").send_photo(
        d.get("photo_url", ""), d.get("caption", ""), d.get("chat_id")
    ),
    "send_telegram_document": lambda d: _get("telegram_out").send_document(
        d.get("document_url", ""), d.get("caption", ""), d.get("chat_id")
    ),
    "get_telegram_updates": lambda d: _get("telegram_out").get_updates(d.get("offset"), d.get("limit", 10)),
    "get_telegram_chat_id": lambda d: _get("telegram_out").get_chat_id_from_updates(),
    "get_sms_status": lambda d: _get("sms").get_message_status(d.get("message_sid", "")),
    "list_recent_sms": lambda d: _get("sms").list_recent_messages(d.get("limit", 10)),
    "slack_add_reaction": lambda d: _get("slack").add_reaction(
        d.get("channel", ""), d.get("timestamp", ""), d.get("emoji", "thumbsup")
    ),
    "slack_upload_file": lambda d: _get("slack").upload_file(
        d.get("channels", ""), d.get("file_path", ""), d.get("title", ""), d.get("initial_comment", "")
    ),
    "slack_set_status": lambda d: _get("slack").set_status(
        d.get("status_text", ""), d.get("emoji", ":speech_balloon:")
    ),
    "discord_list_channels": lambda d: _get("discord").list_channels(d.get("guild_id", "")),
    "discord_add_reaction": lambda d: _get("discord").add_reaction(
        d.get("channel_id", ""), d.get("message_id", ""), d.get("emoji", "\U0001f44d")
    ),
    "discord_delete_message": lambda d: _get("discord").delete_message(
        d.get("channel_id", ""), d.get("message_id", "")
    ),
    "discord_send_webhook_message": lambda d: _get("discord").send_webhook_message(
        d.get("webhook_url", ""), d.get("message", ""), d.get("username", "Ultron")
    ),
    "teams_list_teams": lambda d: _get("teams").list_teams(),
    "teams_list_channels": lambda d: _get("teams").list_channels(d.get("team_id", "")),
    "notion_get_page": lambda d: _get("notion").get_page(d.get("page_id", "")),
    "notion_update_page_properties": lambda d: _get("notion").update_page_properties(
        d.get("page_id", ""), d.get("properties", {})
    ),
    "notion_archive_page": lambda d: _get("notion").archive_page(d.get("page_id", "")),
    "obsidian_delete_note": lambda d: _get("obsidian").delete_note(d.get("note_path", "")),
    "obsidian_list_notes": lambda d: _get("obsidian").list_notes(d.get("folder", "")),
    "obsidian_add_tag": lambda d: _get("obsidian").add_tag(d.get("note_path", ""), d.get("tag", "")),
    "obsidian_push_live": lambda d: _get("obsidian").push_via_rest_api(d.get("note_path", ""), d.get("content", "")),
    "spotify_list_playlists": lambda d: _get("spotify").list_playlists(d.get("limit", 20)),
    # -- Phase 11: Twitter/X -------------------------------------------------
    "twitter_post_tweet": lambda d: _get("twitter").post_tweet(d.get("text", ""), d.get("reply_to_tweet_id")),
    "twitter_delete_tweet": lambda d: _get("twitter").delete_tweet(d.get("tweet_id", "")),
    "twitter_get_user_tweets": lambda d: _get("twitter").get_user_tweets(
        d.get("username", ""), d.get("max_results", 10)
    ),
    # -- Phase 11: LinkedIn ---------------------------------------------------
    "linkedin_get_profile": lambda d: _get("linkedin").get_profile(),
    "linkedin_post_update": lambda d: _get("linkedin").post_update(d.get("text", ""), d.get("visibility", "PUBLIC")),
    # -- Phase 11: Gmail mailbox (integration/ layer over skills/email/gmail.py) --
    "mailbox_unread_count": lambda d: _get("gmail_mailbox").unread_count(),
    "mailbox_latest": lambda d: _get("gmail_mailbox").latest(d.get("max_results", 5)),
}


# ---------------------------------------------------------------------------
# Tool schema definitions (what the model sees) - merged into ai.tools_schema.TOOLS
# ---------------------------------------------------------------------------
NEW_TOOLS = [
    # --- Gmail (OAuth) ----------------------------------------------------
    _tool(
        "gmail_send_email",
        "Send an email via Gmail (OAuth - the user's actual Google account).",
        {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "cc": {"type": "string"},
            "bcc": {"type": "string"},
            "html": {"type": "boolean"},
        },
        ["to", "subject", "body"],
    ),
    _tool(
        "gmail_read_emails",
        "List recent Gmail messages.",
        {"max_results": {"type": "integer"}, "label": {"type": "string"}, "unread_only": {"type": "boolean"}},
    ),
    _tool(
        "gmail_search_emails",
        "Search Gmail using its native search syntax (e.g. 'from:boss is:unread').",
        {"query": {"type": "string"}, "max_results": {"type": "integer"}},
        ["query"],
    ),
    _tool(
        "gmail_get_email_body",
        "Fetch the full body text of one Gmail message.",
        {"message_id": {"type": "string"}},
        ["message_id"],
    ),
    _tool("gmail_mark_as_read", "Mark a Gmail message as read.", {"message_id": {"type": "string"}}, ["message_id"]),
    _tool("gmail_delete_email", "Move a Gmail message to trash.", {"message_id": {"type": "string"}}, ["message_id"]),
    # --- Outlook mail (Graph) -----------------------------------------------
    _tool(
        "outlook_send_email",
        "Send an email via Outlook/Microsoft 365 (Graph API).",
        {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "cc": {"type": "string"},
            "html": {"type": "boolean"},
        },
        ["to", "subject", "body"],
    ),
    _tool(
        "outlook_read_emails",
        "List recent Outlook inbox messages.",
        {"max_results": {"type": "integer"}, "unread_only": {"type": "boolean"}},
    ),
    _tool(
        "outlook_search_emails",
        "Search Outlook mail.",
        {"query": {"type": "string"}, "max_results": {"type": "integer"}},
        ["query"],
    ),
    _tool(
        "outlook_mark_as_read", "Mark an Outlook message as read.", {"message_id": {"type": "string"}}, ["message_id"]
    ),
    _tool("outlook_delete_email", "Delete an Outlook message.", {"message_id": {"type": "string"}}, ["message_id"]),
    # --- Email templates ---------------------------------------------------
    _tool("list_email_templates", "List saved reusable email templates."),
    _tool(
        "render_email_template",
        "Fill a saved email template's {placeholder} fields.",
        {"name": {"type": "string"}, "fields": {"type": "object", "description": "placeholder -> value map"}},
        ["name"],
    ),
    _tool(
        "save_email_template",
        "Save a reusable email template.",
        {"name": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
        ["name", "subject", "body"],
    ),
    # --- Google Calendar -----------------------------------------------------
    _tool(
        "gcal_create_event",
        "Create a Google Calendar event.",
        {
            "title": {"type": "string"},
            "start_time": {"type": "string", "description": "ISO 8601, e.g. 2026-08-05T14:00:00"},
            "end_time": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "timezone": {"type": "string"},
        },
        ["title", "start_time", "end_time"],
    ),
    _tool("gcal_list_events", "List upcoming Google Calendar events.", {"max_results": {"type": "integer"}}),
    _tool(
        "gcal_update_event",
        "Update fields of a Google Calendar event.",
        {"event_id": {"type": "string"}, "fields": {"type": "object"}},
        ["event_id"],
    ),
    _tool("gcal_delete_event", "Delete a Google Calendar event.", {"event_id": {"type": "string"}}, ["event_id"]),
    _tool(
        "gcal_find_free_slots",
        "Find free time slots on a given date in Google Calendar.",
        {
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "duration_minutes": {"type": "integer"},
            "day_start": {"type": "string"},
            "day_end": {"type": "string"},
        },
        ["date"],
    ),
    # --- Outlook Calendar ------------------------------------------------
    _tool(
        "outlook_cal_create_event",
        "Create an Outlook/Microsoft 365 Calendar event.",
        {
            "title": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
        },
        ["title", "start_time", "end_time"],
    ),
    _tool("outlook_cal_list_events", "List upcoming Outlook Calendar events.", {"max_results": {"type": "integer"}}),
    _tool(
        "outlook_cal_delete_event", "Delete an Outlook Calendar event.", {"event_id": {"type": "string"}}, ["event_id"]
    ),
    # --- Provider-agnostic scheduler ---------------------------------------
    _tool(
        "schedule_meeting",
        "Schedule a meeting on whichever cloud calendar (Google/Outlook) is configured.",
        {
            "title": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
        },
        ["title", "start_time", "end_time"],
    ),
    _tool(
        "list_upcoming_meetings",
        "List upcoming meetings from the configured cloud calendar.",
        {"max_results": {"type": "integer"}},
    ),
    _tool(
        "cancel_meeting",
        "Cancel a meeting on the configured cloud calendar.",
        {"event_id": {"type": "string"}},
        ["event_id"],
    ),
    _tool(
        "reschedule_meeting",
        "Move a meeting to a new start/end time.",
        {"event_id": {"type": "string"}, "new_start": {"type": "string"}, "new_end": {"type": "string"}},
        ["event_id", "new_start", "new_end"],
    ),
    _tool(
        "find_free_meeting_slot",
        "Find a free slot for a meeting on a given date.",
        {"date": {"type": "string"}, "duration_minutes": {"type": "integer"}},
        ["date"],
    ),
    _tool("daily_meeting_agenda", "Get today's meetings from the configured cloud calendar."),
    # --- Web scraping / research --------------------------------------------
    _tool(
        "scrape_links",
        "Extract all links from a web page.",
        {"url": {"type": "string"}, "same_domain_only": {"type": "boolean"}},
        ["url"],
    ),
    _tool("scrape_images", "Extract all image URLs from a web page.", {"url": {"type": "string"}}, ["url"]),
    _tool(
        "scrape_tables", "Extract HTML tables from a web page as structured rows.", {"url": {"type": "string"}}, ["url"]
    ),
    _tool(
        "scrape_selector",
        "Extract text of every element matching a CSS selector on a page.",
        {"url": {"type": "string"}, "selector": {"type": "string"}},
        ["url", "selector"],
    ),
    _tool(
        "scrape_page_metadata",
        "Get a page's title, description, and Open Graph metadata.",
        {"url": {"type": "string"}},
        ["url"],
    ),
    _tool(
        "deep_research",
        "Run multi-query web research and synthesize a cited summary.",
        {"query": {"type": "string"}, "num_queries": {"type": "integer"}, "results_per_query": {"type": "integer"}},
        ["query"],
    ),
    # --- Form filling (Selenium) --------------------------------------------
    # fill_web_form schema intentionally omitted - see matching comment
    # next to NEW_DIRECT_HANDLERS above; canonical gated schema entry
    # lives in ai/phase30_gated_tools.py.
    _tool(
        "extract_rendered_page",
        "Load a JS-heavy page and return its fully-rendered HTML.",
        {"url": {"type": "string"}, "wait_selector": {"type": "string"}},
        ["url"],
    ),
    # --- Data: Excel / CSV / JSON --------------------------------------------
    _tool(
        "read_excel_sheet",
        "Read rows from an Excel (.xlsx) sheet.",
        {"path": {"type": "string"}, "sheet_name": {"type": "string"}, "max_rows": {"type": "integer"}},
        ["path"],
    ),
    _tool(
        "create_excel_workbook",
        "Create a new Excel workbook from row data.",
        {
            "path": {"type": "string"},
            "data": {"type": "array", "items": {"type": "object"}},
            "sheet_name": {"type": "string"},
        },
        ["path", "data"],
    ),
    _tool(
        "filter_excel_rows",
        "Filter Excel rows where a column equals a value.",
        {"path": {"type": "string"}, "column": {"type": "string"}, "value": {}},
        ["path", "column", "value"],
    ),
    _tool(
        "aggregate_excel_column",
        "Aggregate (sum/avg/min/max/count) an Excel column.",
        {"path": {"type": "string"}, "column": {"type": "string"}, "operation": {"type": "string"}},
        ["path", "column"],
    ),
    _tool(
        "read_csv_file",
        "Read rows from a CSV file.",
        {"path": {"type": "string"}, "max_rows": {"type": "integer"}},
        ["path"],
    ),
    _tool(
        "write_csv_file",
        "Write rows to a CSV file.",
        {"path": {"type": "string"}, "rows": {"type": "array", "items": {"type": "object"}}},
        ["path", "rows"],
    ),
    _tool(
        "filter_csv_rows",
        "Filter CSV rows where a column equals a value.",
        {"path": {"type": "string"}, "column": {"type": "string"}, "value": {}},
        ["path", "column", "value"],
    ),
    _tool(
        "sort_csv_rows",
        "Sort CSV rows by a column.",
        {
            "path": {"type": "string"},
            "column": {"type": "string"},
            "descending": {"type": "boolean"},
            "numeric": {"type": "boolean"},
        },
        ["path", "column"],
    ),
    _tool(
        "aggregate_csv_column",
        "Aggregate (sum/avg/min/max/count) a CSV column.",
        {"path": {"type": "string"}, "column": {"type": "string"}, "operation": {"type": "string"}},
        ["path", "column"],
    ),
    _tool("read_json_file", "Read a JSON file.", {"path": {"type": "string"}}, ["path"]),
    _tool("write_json_file", "Write data to a JSON file.", {"path": {"type": "string"}, "data": {}}, ["path", "data"]),
    _tool(
        "get_json_path",
        "Get a nested value from a JSON file by dot-path (e.g. 'users.0.name').",
        {"path": {"type": "string"}, "dot_path": {"type": "string"}},
        ["path", "dot_path"],
    ),
    _tool(
        "set_json_path",
        "Set a nested value in a JSON file by dot-path.",
        {"path": {"type": "string"}, "dot_path": {"type": "string"}, "value": {}},
        ["path", "dot_path", "value"],
    ),
    # --- Communication -------------------------------------------------
    _tool(
        "send_whatsapp_message",
        "Send a WhatsApp message via the WhatsApp BUSINESS API (Twilio/Meta Cloud API) - "
        "requires a real phone number you already have, and requires WHATSAPP_ACCESS_TOKEN "
        "to be configured in .env. DO NOT use this for a saved contact's NAME (e.g. 'message "
        "Mummy on WhatsApp') and do not guess or invent a phone number - use "
        "whatsapp_send_message_by_name instead, which searches WhatsApp Desktop's own contact "
        "list by name and asks the user to pick if more than one match exists.",
        {"to": {"type": "string", "description": "International format, no '+'"}, "message": {"type": "string"}},
        ["to", "message"],
    ),
    _tool(
        "send_whatsapp_template",
        "Send a pre-approved WhatsApp template message.",
        {
            "to": {"type": "string"},
            "template_name": {"type": "string"},
            "language_code": {"type": "string"},
            "params": {"type": "array", "items": {"type": "string"}},
        },
        ["to", "template_name"],
    ),
    _tool(
        "send_telegram_message",
        "Push a Telegram message (outbound notification).",
        {"message": {"type": "string"}, "chat_id": {"type": "string"}},
        ["message"],
    ),
    _tool(
        "send_sms",
        "Send an SMS via Twilio.",
        {"to": {"type": "string"}, "message": {"type": "string"}},
        ["to", "message"],
    ),
    # --- Slack --------------------------------------------------------------
    _tool(
        "slack_send_message",
        "Send a Slack message to a channel.",
        {"channel": {"type": "string"}, "text": {"type": "string"}, "thread_ts": {"type": "string"}},
        ["channel", "text"],
    ),
    _tool(
        "slack_read_channel",
        "Read recent Slack channel history.",
        {"channel": {"type": "string"}, "limit": {"type": "integer"}},
        ["channel"],
    ),
    _tool("slack_list_channels", "List Slack channels the bot can see.", {"limit": {"type": "integer"}}),
    # --- Discord -------------------------------------------------------
    _tool(
        "discord_send_message",
        "Send a Discord message to a channel.",
        {"channel_id": {"type": "string"}, "message": {"type": "string"}},
        ["channel_id", "message"],
    ),
    _tool(
        "discord_read_channel",
        "Read recent Discord channel history.",
        {"channel_id": {"type": "string"}, "limit": {"type": "integer"}},
        ["channel_id"],
    ),
    # --- Teams --------------------------------------------------------------
    _tool(
        "teams_send_webhook_message",
        "Post a message card to a Teams channel via incoming webhook.",
        {"title": {"type": "string"}, "message": {"type": "string"}, "webhook_url": {"type": "string"}},
        ["title", "message"],
    ),
    _tool(
        "teams_send_channel_message",
        "Send a message to a Teams channel via Graph API.",
        {"team_id": {"type": "string"}, "channel_id": {"type": "string"}, "message": {"type": "string"}},
        ["team_id", "channel_id", "message"],
    ),
    # --- Notion -------------------------------------------------------------
    _tool(
        "notion_create_page",
        "Create a new Notion page (in a page or database).",
        {
            "parent_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "is_database": {"type": "boolean"},
        },
        ["parent_id", "title"],
    ),
    _tool(
        "notion_append_text",
        "Append a paragraph of text to a Notion page.",
        {"page_id": {"type": "string"}, "text": {"type": "string"}},
        ["page_id", "text"],
    ),
    _tool(
        "notion_query_database",
        "Query a Notion database.",
        {"database_id": {"type": "string"}, "filter_obj": {"type": "object"}, "page_size": {"type": "integer"}},
        ["database_id"],
    ),
    _tool(
        "notion_search",
        "Search Notion pages/databases by title.",
        {"query": {"type": "string"}, "filter_type": {"type": "string", "description": "'page' or 'database'"}},
        ["query"],
    ),
    # --- Obsidian ------------------------------------------------------
    _tool(
        "obsidian_create_note",
        "Create a new note in the Obsidian vault.",
        {"note_path": {"type": "string"}, "content": {"type": "string"}, "overwrite": {"type": "boolean"}},
        ["note_path"],
    ),
    _tool(
        "obsidian_read_note", "Read a note from the Obsidian vault.", {"note_path": {"type": "string"}}, ["note_path"]
    ),
    _tool(
        "obsidian_append_note",
        "Append text to an existing Obsidian note.",
        {"note_path": {"type": "string"}, "text": {"type": "string"}},
        ["note_path", "text"],
    ),
    _tool(
        "obsidian_append_daily_note",
        "Append text to today's Obsidian daily note.",
        {"text": {"type": "string"}, "daily_folder": {"type": "string"}},
        ["text"],
    ),
    _tool(
        "obsidian_search_vault",
        "Full-text search across the Obsidian vault.",
        {"query": {"type": "string"}, "max_results": {"type": "integer"}},
        ["query"],
    ),
    _tool(
        "obsidian_get_backlinks",
        "Find every note linking to a given note.",
        {"note_name": {"type": "string"}},
        ["note_name"],
    ),
    # --- Spotify --------------------------------------------------------
    _tool(
        "spotify_search_track",
        "Search Spotify for a track.",
        {"query": {"type": "string"}, "limit": {"type": "integer"}},
        ["query"],
    ),
    _tool(
        "spotify_play",
        "Start/resume Spotify playback, optionally a specific track.",
        {"track_uri": {"type": "string"}, "device_id": {"type": "string"}},
    ),
    _tool("spotify_pause", "Pause Spotify playback."),
    _tool("spotify_next_track", "Skip to the next Spotify track."),
    _tool("spotify_previous_track", "Go to the previous Spotify track."),
    _tool("spotify_set_volume", "Set Spotify playback volume (0-100).", {"percent": {"type": "integer"}}, ["percent"]),
    _tool("spotify_current_playback", "Get what's currently playing on Spotify."),
    # --- YouTube Data API ------------------------------------------------
    _tool(
        "youtube_data_search",
        "Search YouTube videos (structured metadata via the Data API).",
        {"query": {"type": "string"}, "max_results": {"type": "integer"}},
        ["query"],
    ),
    _tool(
        "youtube_video_details",
        "Get stats/details for a YouTube video by ID.",
        {"video_id": {"type": "string"}},
        ["video_id"],
    ),
    _tool(
        "youtube_channel_details",
        "Get stats/details for a YouTube channel.",
        {"channel_id": {"type": "string"}, "handle": {"type": "string"}},
    ),
    _tool(
        "youtube_playlist_items",
        "List items in a YouTube playlist.",
        {"playlist_id": {"type": "string"}, "max_results": {"type": "integer"}},
        ["playlist_id"],
    ),
    _tool(
        "youtube_video_comments",
        "Get top comments on a YouTube video.",
        {"video_id": {"type": "string"}, "max_results": {"type": "integer"}},
        ["video_id"],
    ),
    # --- Round 2: remaining methods not covered in the first wiring pass ---
    _tool("get_email_template", "Get a saved email template's subject/body.", {"name": {"type": "string"}}, ["name"]),
    _tool("delete_email_template", "Delete a saved email template.", {"name": {"type": "string"}}, ["name"]),
    _tool(
        "outlook_cal_update_event",
        "Update fields of an Outlook Calendar event.",
        {"event_id": {"type": "string"}, "fields": {"type": "object"}},
        ["event_id"],
    ),
    _tool(
        "gather_research_sources",
        "Gather raw web sources for a query without AI summarization (search + read top pages).",
        {
            "query": {"type": "string"},
            "num_queries": {"type": "integer"},
            "results_per_query": {"type": "integer"},
            "read_top_n": {"type": "integer"},
        },
        ["query"],
    ),
    _tool(
        "click_web_element",
        "Click an element on a web page (Selenium-driven automated browser).",
        {"url": {"type": "string"}, "selector": {"type": "string"}, "by": {"type": "string"}},
        ["url", "selector"],
    ),
    _tool("close_form_filler_browser", "Close the automated Selenium browser session used for form filling."),
    _tool("list_excel_sheets", "List the sheet names in an Excel workbook.", {"path": {"type": "string"}}, ["path"]),
    _tool(
        "append_excel_rows",
        "Append rows to an existing Excel sheet.",
        {
            "path": {"type": "string"},
            "rows": {"type": "array", "items": {"type": "object"}},
            "sheet_name": {"type": "string"},
        },
        ["path", "rows"],
    ),
    _tool(
        "add_excel_formula",
        "Set a cell to a formula in an Excel workbook.",
        {
            "path": {"type": "string"},
            "cell": {"type": "string"},
            "formula": {"type": "string"},
            "sheet_name": {"type": "string"},
        },
        ["path", "cell", "formula"],
    ),
    _tool(
        "append_csv_rows",
        "Append rows to a CSV file.",
        {"path": {"type": "string"}, "rows": {"type": "array", "items": {"type": "object"}}},
        ["path", "rows"],
    ),
    _tool(
        "csv_to_json",
        "Convert a CSV file's rows into a JSON-friendly list of dicts.",
        {"path": {"type": "string"}},
        ["path"],
    ),
    _tool(
        "merge_json_file",
        "Shallow-merge new key/values into the top level of a JSON file.",
        {"path": {"type": "string"}, "updates": {"type": "object"}},
        ["path", "updates"],
    ),
    _tool(
        "query_json_list",
        "Filter a list nested in a JSON file where a key equals a value.",
        {
            "path": {"type": "string"},
            "list_dot_path": {"type": "string"},
            "filter_key": {"type": "string"},
            "filter_value": {},
        },
        ["path", "list_dot_path", "filter_key", "filter_value"],
    ),
    _tool(
        "send_whatsapp_media",
        "Send an image/document/video/audio via WhatsApp.",
        {
            "to": {"type": "string"},
            "media_url": {"type": "string"},
            "media_type": {"type": "string"},
            "caption": {"type": "string"},
        },
        ["to", "media_url"],
    ),
    _tool("mark_whatsapp_read", "Mark a WhatsApp message as read.", {"message_id": {"type": "string"}}, ["message_id"]),
    _tool(
        "send_telegram_photo",
        "Push a photo to Telegram.",
        {"photo_url": {"type": "string"}, "caption": {"type": "string"}, "chat_id": {"type": "string"}},
        ["photo_url"],
    ),
    _tool(
        "send_telegram_document",
        "Push a document to Telegram.",
        {"document_url": {"type": "string"}, "caption": {"type": "string"}, "chat_id": {"type": "string"}},
        ["document_url"],
    ),
    _tool(
        "get_telegram_updates",
        "Poll for incoming Telegram messages.",
        {"offset": {"type": "integer"}, "limit": {"type": "integer"}},
    ),
    _tool("get_telegram_chat_id", "Discover the chat_id to message, from recent updates (first-time setup helper)."),
    _tool(
        "get_sms_status",
        "Check the delivery status of a sent SMS.",
        {"message_sid": {"type": "string"}},
        ["message_sid"],
    ),
    _tool("list_recent_sms", "List recently sent/received SMS messages.", {"limit": {"type": "integer"}}),
    _tool(
        "slack_add_reaction",
        "Add an emoji reaction to a Slack message.",
        {"channel": {"type": "string"}, "timestamp": {"type": "string"}, "emoji": {"type": "string"}},
        ["channel", "timestamp"],
    ),
    _tool(
        "slack_upload_file",
        "Upload a file to a Slack channel.",
        {
            "channels": {"type": "string"},
            "file_path": {"type": "string"},
            "title": {"type": "string"},
            "initial_comment": {"type": "string"},
        },
        ["channels", "file_path"],
    ),
    _tool(
        "slack_set_status",
        "Set the bot's Slack status.",
        {"status_text": {"type": "string"}, "emoji": {"type": "string"}},
        ["status_text"],
    ),
    _tool(
        "discord_list_channels", "List channels in a Discord server.", {"guild_id": {"type": "string"}}, ["guild_id"]
    ),
    _tool(
        "discord_add_reaction",
        "Add an emoji reaction to a Discord message.",
        {"channel_id": {"type": "string"}, "message_id": {"type": "string"}, "emoji": {"type": "string"}},
        ["channel_id", "message_id"],
    ),
    _tool(
        "discord_delete_message",
        "Delete a Discord message.",
        {"channel_id": {"type": "string"}, "message_id": {"type": "string"}},
        ["channel_id", "message_id"],
    ),
    _tool(
        "discord_send_webhook_message",
        "Post to Discord via a channel webhook URL (no bot invite needed).",
        {"webhook_url": {"type": "string"}, "message": {"type": "string"}, "username": {"type": "string"}},
        ["webhook_url", "message"],
    ),
    _tool("teams_list_teams", "List Microsoft Teams the user has joined."),
    _tool("teams_list_channels", "List channels in a Microsoft Team.", {"team_id": {"type": "string"}}, ["team_id"]),
    _tool("notion_get_page", "Get a Notion page's full data.", {"page_id": {"type": "string"}}, ["page_id"]),
    _tool(
        "notion_update_page_properties",
        "Update a Notion page's properties.",
        {"page_id": {"type": "string"}, "properties": {"type": "object"}},
        ["page_id", "properties"],
    ),
    _tool("notion_archive_page", "Archive (soft-delete) a Notion page.", {"page_id": {"type": "string"}}, ["page_id"]),
    _tool(
        "obsidian_delete_note",
        "Delete a note from the Obsidian vault.",
        {"note_path": {"type": "string"}},
        ["note_path"],
    ),
    _tool(
        "obsidian_list_notes",
        "List notes in the Obsidian vault (optionally under a folder).",
        {"folder": {"type": "string"}},
    ),
    _tool(
        "obsidian_add_tag",
        "Append a #tag to an Obsidian note.",
        {"note_path": {"type": "string"}, "tag": {"type": "string"}},
        ["note_path", "tag"],
    ),
    _tool(
        "obsidian_push_live",
        "Push a note update into a currently-open Obsidian instance via the Local REST API plugin.",
        {"note_path": {"type": "string"}, "content": {"type": "string"}},
        ["note_path", "content"],
    ),
    _tool("spotify_list_playlists", "List the user's Spotify playlists.", {"limit": {"type": "integer"}}),
    # --- Phase 11: Twitter/X -------------------------------------------------
    _tool(
        "twitter_post_tweet",
        "Post a tweet, optionally as a reply.",
        {"text": {"type": "string"}, "reply_to_tweet_id": {"type": "string"}},
        ["text"],
    ),
    _tool("twitter_delete_tweet", "Delete a tweet by ID.", {"tweet_id": {"type": "string"}}, ["tweet_id"]),
    _tool(
        "twitter_get_user_tweets",
        "Get a user's recent tweets by username.",
        {"username": {"type": "string"}, "max_results": {"type": "integer"}},
        ["username"],
    ),
    # --- Phase 11: LinkedIn ----------------------------------------------------
    _tool("linkedin_get_profile", "Get the authenticated LinkedIn user's basic profile."),
    _tool(
        "linkedin_post_update",
        "Post a text update to the authenticated user's LinkedIn feed.",
        {"text": {"type": "string"}, "visibility": {"type": "string"}},
        ["text"],
    ),
    # --- Phase 11: Gmail mailbox -------------------------------------------------
    _tool("mailbox_unread_count", "Count unread emails in the Gmail inbox."),
    _tool(
        "mailbox_latest",
        "Get the most recent Gmail emails regardless of read state.",
        {"max_results": {"type": "integer"}},
    ),
]
