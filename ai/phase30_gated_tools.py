"""
PHASE 30 - GATED TOOLS (audit fix, item #4, real-world-reach batch)
=====================================================================
The other half of the 20-orphaned-packages fix (see
ai/phase30_extended_tools.py for the safe half). These wrap
capabilities that reach outside Ultron's own process - notifying your
other devices, posting to your social accounts, driving a real browser
- so each is gated behind its own env flag, off by default, exactly
like this project already does for ULTRON_AUTONOMY_ENABLED and
ULTRON_ORCHESTRATOR_ENABLED. The tool schema for a disabled capability
is not even sent to the model - not just refused at call time - so
there's no chance of the model attempting something that's off.

  devices/          -> notify_all_devices          (ULTRON_DEVICES_ENABLED)
  autonomous_web/    -> post_to_social_media,
                        extract_web_data,
                        fill_web_form                (ULTRON_AUTONOMOUS_WEB_ENABLED)

Deliberately NOT wired at all, even gated: networking/ (raw SSH/FTP
clients - arbitrary remote code/file access is a different order of
risk than anything else in this batch; if you need this, wire the
specific host/command patterns you actually use, reviewed by hand,
rather than a general-purpose exec-anything tool). cross_device/'s
websocket server is a background listener, not a call-and-return
action - see core/assistant.py (ULTRON_CROSS_DEVICE_ENABLED) instead.
"""

import os
from typing import Dict


def _devices_enabled() -> bool:
    return os.getenv("ULTRON_DEVICES_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def _autonomous_web_enabled() -> bool:
    return os.getenv("ULTRON_AUTONOMOUS_WEB_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def _notify_all_devices(args: Dict) -> Dict:
    if not _devices_enabled():
        return {"success": False, "error": "Disabled. Set ULTRON_DEVICES_ENABLED=true in .env to enable."}
    title = str(args.get("title", "")).strip()
    message = str(args.get("message", "")).strip()
    if not title or not message:
        return {"success": False, "error": "title and message are required."}
    try:
        from devices.sync_all import SyncAll

        return {"success": True, **SyncAll().notify_all(title, message)}
    except Exception as e:
        return {"success": False, "error": f"Device notify failed: {e}"}


def _post_to_social_media(args: Dict) -> Dict:
    if not _autonomous_web_enabled():
        return {"success": False, "error": "Disabled. Set ULTRON_AUTONOMOUS_WEB_ENABLED=true in .env to enable."}
    platform = str(args.get("platform", "")).strip().lower()
    text = str(args.get("text", "")).strip()
    webhook_url = args.get("webhook_url")
    if not platform or not text:
        return {"success": False, "error": "platform and text are required."}

    try:
        from autonomous_web.social_media_agent import SocialMediaAgent

        agent = SocialMediaAgent()

        if platform == "twitter":
            bearer = os.getenv("TWITTER_BEARER_TOKEN")
            if not bearer:
                return {"success": False, "error": "TWITTER_BEARER_TOKEN not set in .env."}
            agent.configure("twitter", bearer_token=bearer)
            result = agent.post_to_twitter(text)
        elif webhook_url:
            result = agent.post_to_webhook(platform, webhook_url, {"content": text})
        else:
            return {
                "success": False,
                "error": "For platform='twitter', TWITTER_BEARER_TOKEN in .env is used. "
                "For anything else, pass webhook_url.",
            }

        return {
            "success": result.success,
            "platform": result.platform,
            "post_id": result.post_id,
            "error": result.error,
        }
    except Exception as e:
        return {"success": False, "error": f"Social post failed: {e}"}


def _run_web_agent(url: str, action):
    """Shared browser lifecycle: start, navigate, run the given callable
    with the page, always stop - so no gated tool call leaks a browser
    process if it raises partway through."""
    from autonomous_web.web_agent_core import WebAgentCore

    with WebAgentCore() as agent:
        page = agent.new_page()
        page.goto(url)
        return action(agent, page)


def _extract_web_data(args: Dict) -> Dict:
    if not _autonomous_web_enabled():
        return {"success": False, "error": "Disabled. Set ULTRON_AUTONOMOUS_WEB_ENABLED=true in .env to enable."}
    url = str(args.get("url", "")).strip()
    if not url:
        return {"success": False, "error": "url is required."}
    mode = str(args.get("mode", "table")).strip()
    selector = str(args.get("selector", "table")).strip()

    try:
        from autonomous_web.data_extractor import DataExtractor

        def do_extract(agent, page):
            extractor = DataExtractor(page)
            if mode == "links":
                return extractor.extract_links(selector or "body")
            if mode == "matching":
                return extractor.extract_all_matching(selector)
            return extractor.extract_table(selector or "table")

        data = _run_web_agent(url, do_extract)
        return {"success": True, "url": url, "mode": mode, "data": data}
    except Exception as e:
        return {"success": False, "error": f"Web extraction failed: {e}"}


def _fill_web_form(args: Dict) -> Dict:
    if not _autonomous_web_enabled():
        return {"success": False, "error": "Disabled. Set ULTRON_AUTONOMOUS_WEB_ENABLED=true in .env to enable."}
    url = str(args.get("url", "")).strip()
    field_values = args.get("field_values") or {}
    submit_selector = args.get("submit_selector")
    if not url or not field_values:
        return {"success": False, "error": "url and field_values ({selector: value}) are required."}

    try:
        from autonomous_web.form_filler import FormFiller

        def do_fill(agent, page):
            filler = FormFiller(page)
            fill_results = filler.fill_from_dict(field_values)
            submitted = filler.submit(submit_selector) if submit_selector else None
            has_errors = filler.has_validation_errors()
            return {"fields_filled": fill_results, "submitted": submitted, "validation_errors": has_errors}

        result = _run_web_agent(url, do_fill)
        return {"success": True, "url": url, **result}
    except Exception as e:
        return {"success": False, "error": f"Form fill failed: {e}"}


PHASE30_GATED_DIRECT_HANDLERS = {
    "notify_all_devices": _notify_all_devices,
    "post_to_social_media": _post_to_social_media,
    "extract_web_data": _extract_web_data,
    "fill_web_form": _fill_web_form,
}


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        },
    }


# Schema visibility itself is gated - the model never sees a tool it
# can't use, it doesn't just get refused after trying.
PHASE30_GATED_TOOLS = []

if _devices_enabled():
    PHASE30_GATED_TOOLS.append(
        _tool(
            "notify_all_devices",
            "Send a notification to all paired personal devices (phone, watch, etc).",
            {
                "title": {"type": "string", "description": "Notification title."},
                "message": {"type": "string", "description": "Notification body."},
            },
            ["title", "message"],
        )
    )

if _autonomous_web_enabled():
    PHASE30_GATED_TOOLS.extend(
        [
            _tool(
                "post_to_social_media",
                "Post text content to the user's own social media account (Twitter/X via API token, "
                "or any platform with a webhook URL). Only ever posts what the user explicitly asked to post.",
                {
                    "platform": {
                        "type": "string",
                        "description": "'twitter' or a custom name paired with webhook_url.",
                    },
                    "text": {"type": "string", "description": "The content to post."},
                    "webhook_url": {"type": "string", "description": "Required for non-twitter platforms."},
                },
                ["platform", "text"],
            ),
            _tool(
                "extract_web_data",
                "Open a webpage in a real browser and extract structured data (a table, links, or elements matching a CSS selector).",
                {
                    "url": {"type": "string", "description": "Page URL to open."},
                    "mode": {"type": "string", "description": "'table' (default), 'links', or 'matching'."},
                    "selector": {
                        "type": "string",
                        "description": "CSS selector - table selector, link container, or match selector depending on mode.",
                    },
                },
                ["url"],
            ),
            _tool(
                "fill_web_form",
                "Open a webpage in a real browser, fill in form fields, and optionally submit.",
                {
                    "url": {"type": "string", "description": "Page URL with the form."},
                    "field_values": {
                        "type": "object",
                        "description": "Map of CSS selector -> value to type into each field.",
                    },
                    "submit_selector": {
                        "type": "string",
                        "description": "CSS selector of the submit button, if it should be clicked.",
                    },
                },
                ["url", "field_values"],
            ),
        ]
    )
