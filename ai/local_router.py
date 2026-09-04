"""
Local intent router (smart router)
===================================
Fast-path for two kinds of speech that should never have to wait on a
Groq round-trip:

  1. App-control commands - "UI mode on", "text mode off", "silent mode
     on", "stop"/"cancel" - these change how Ultron itself behaves and
     aren't questions for the LLM at all.
  2. Simple, unambiguous system commands - "what time is it", "open
     Chrome", "volume up", "mute" - these map directly onto an existing
     skill/tool, so answering them locally is both faster (no network
     round-trip to Groq) and cheaper (no tokens spent).

Anything that doesn't match one of these patterns falls straight through
(``matched=False``) to the normal brain (ai/router.py -> Groq), which is
where real questions, multi-step tasks, and anything needing reasoning or
tool-chaining still go. This module never tries to be clever about
ambiguous phrasing - if a match isn't confident, it backs off to the LLM
rather than risk misinterpreting the user.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ai.tool_runtime import execute_tool_call as execute_tool


def _parsed(tool_name: str, arguments: Optional[dict] = None) -> dict:
    """Call execute_tool() and parse its JSON string result back into a
    dict, so the read-only fast-path replies below can format numbers
    directly instead of just echoing the raw tool output."""
    raw = execute_tool(tool_name, arguments or {})
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"error": raw}


_WAKE_PREFIX_RE = re.compile(r"^\s*(?:hi|hey|hello|yo|ok|okay)?[\s,]*ultron\s*[,:]?\s*", re.IGNORECASE)


def strip_wake_prefix(text: str) -> str:
    """Strip a leading address/wake-word phrase ("hi ultron", "hey ultron",
    "ultron,", ...) from input text. Voice mode's wake-word detector
    already removes this before handle_command() ever sees the text (see
    core.assistant.Assistant.run_listen's on_wake callback, which passes
    only the *remainder* after the wake word) - but typed input
    (run_text/run_voice_typed) has no equivalent step, so someone typing
    "hi ultron, time batao" out of habit would otherwise reach
    route_system_command/complexity_router.classify with the address
    prefix still attached. That matters here specifically because a
    short casual-sounding opener like "hi" can otherwise shadow a real
    command or question that follows it (e.g. complexity_router's
    casual-chat allowlist matching "hi" and routing the *whole* message
    to the tool-free fast tier even though "...cpu kitna use ho raha
    hai" needed a real tool). Idempotent - safe to call on text with no
    such prefix, and never returns an empty string (falls back to the
    original text if stripping the prefix would leave nothing, e.g. the
    message really was just "hi ultron" on its own)."""
    stripped = _WAKE_PREFIX_RE.sub("", text, count=1).strip()
    return stripped or text.strip()


# Control actions handled by main.py's runtime (mode toggles, interrupt).
CONTROL_PATTERNS = [
    (re.compile(r"^\s*(ui|overlay)\s*mode\s*(on|enable|start)\s*$", re.I), "ui_on"),
    (re.compile(r"^\s*(ui|overlay)\s*mode\s*(off|disable|stop)\s*$", re.I), "ui_off"),
    (re.compile(r"^\s*(open|show|launch)\s*(the\s*)?dashboard\s*$", re.I), "dashboard_on"),
    (re.compile(r"^\s*dashboard\s*(mode\s*)?(on|enable|start|kholo|khol\s*do)\s*$", re.I), "dashboard_on"),
    (re.compile(r"^\s*text\s*mode\s*(on|enable|start)\s*$", re.I), "text_on"),
    (re.compile(r"^\s*text\s*mode\s*(off|disable|stop)\s*$", re.I), "text_off"),
    (re.compile(r"^\s*silent\s*mode\s*(on|enable|start)\s*$", re.I), "silent_on"),
    (re.compile(r"^\s*silent\s*mode\s*(off|disable|stop)\s*$", re.I), "silent_off"),
    # Runtime toggle for core.control_mode's SAFE category (non-destructive
    # tools auto-run without waiting on trust_policy's learned-confidence
    # ramp-up) - flips core.control_mode's in-memory override instantly, no
    # .env edit or restart needed. Deliberately SAFE-only: the UNSAFE
    # category (destructive tools, zero confirmation) stays .env+restart
    # only, on purpose - see core/control_mode.py's module docstring.
    (re.compile(r"^\s*(auto|autonomous|full\s*auto)\s*mode\s*(on|enable|start)\s*$", re.I), "auto_safe_on"),
    (re.compile(r"^\s*sab\s*(khud|khood)\s*kar(o|do)\s*$", re.I), "auto_safe_on"),
    (re.compile(r"^\s*(auto|autonomous|full\s*auto)\s*mode\s*(off|disable|stop)\s*$", re.I), "auto_safe_off"),
    (re.compile(r"^\s*(normal|manual)\s*mode\s*(on|wapas)?\s*$", re.I), "auto_safe_off"),
    (re.compile(r"^\s*(stop|cancel|shut\s*up|never\s*mind)\s*$", re.I), "stop"),
]


@dataclass
class RouteResult:
    matched: bool
    action: Optional[str] = None  # control action for main.py to apply
    response: Optional[str] = None  # spoken/printed reply, if any
    handled_locally: bool = False  # True if a system command already ran


def check_control_command(text: str) -> Optional[str]:
    """Return a control action name if `text` is a mode/interrupt command,
    else None. Checked first, before system-command matching."""
    cleaned = strip_wake_prefix(text).strip()
    for pattern, action in CONTROL_PATTERNS:
        if pattern.match(cleaned):
            return action
    return None


def _reply(text: str) -> RouteResult:
    return RouteResult(matched=True, response=text, handled_locally=True)


def _introspection_reply() -> Optional[str]:
    """Best-effort answer for "what are you doing right now" style
    queries, sourced from PHASE_18_1_CORE_FOUNDATION's consciousness.py
    (see core/assistant.py's Phase 18 observer layer). Returns None if
    that module isn't available (a checkout without
    PHASE_18_1_CORE_FOUNDATION/ present) or reflect() itself fails, so
    the caller can fall through to the normal 'no local match' behavior
    rather than claiming a status Ultron doesn't actually have."""
    try:
        from core.consciousness_p18 import get_consciousness

        state = get_consciousness().reflect()
    except Exception:
        return None

    if not state.get("focus"):
        parts = [f"Idle at the moment, Sir - confidence is at {state['confidence']:.0%}."]
    else:
        parts = [f"Working on \"{state['focus']}\", Sir - confidence is at {state['confidence']:.0%}."]
    if state.get("attention_depth", 0) > 1:
        parts.append(f"{state['attention_depth']} things are currently stacked up.")
    if state.get("active_background_tasks"):
        parts.append(f"{state['active_background_tasks']} background task(s) running.")
    if state.get("recent_setbacks"):
        parts.append(
            f"{state['recent_setbacks']} recent setback(s) out of the last {state['outcomes_tracked']} attempts."
        )
    return " ".join(parts)


def route_system_command(text: str) -> Optional[RouteResult]:
    """Try to answer `text` entirely locally via an existing skill/tool.
    Returns None if nothing matched confidently (caller should fall
    through to the LLM)."""
    t = strip_wake_prefix(text).strip().lower().rstrip(".!? ")

    if re.match(
        r"^(what are you (doing|working on)( right now)?|what'?s your status|"
        r"status report|are you (busy|idle))\??$",
        t,
    ):
        introspection = _introspection_reply()
        if introspection is not None:
            return _reply(introspection)
        # Phase 18 observer layer unavailable - fall through to the LLM
        # exactly as this query would have been handled before it existed.

    if re.match(
        r"^(what'?s the time|what is the time|what time is it|current time|tell me the time|time please|time batao|abhi kitne baje hai|kitne baje hai|samay batao)$",
        t,
    ):
        return _reply(f"It's {datetime.now().strftime('%I:%M %p')}, Sir.")

    if re.match(
        r"^(what'?s the date|what is the date|current date|today'?s date|what day is it|what'?s today'?s date|date batao|aaj (ki )?date (kya hai|batao)|aaj kya (din|tarikh) hai)$",
        t,
    ):
        return _reply(f"Today is {datetime.now().strftime('%A, %B %d, %Y')}, Sir.")

    m = re.match(r"^(?:set |change )?volume(?: to| level)? (\d{1,3})(?: ?%| percent)?$", t)
    if m:
        level = max(0, min(100, int(m.group(1))))
        execute_tool("set_volume", {"level": level})
        return _reply(f"Volume set to {level} percent, Sir.")

    if re.match(r"^(volume up|increase volume|turn (the )?volume up|louder)$", t):
        execute_tool("media_volume_up", {})
        return _reply("Turning it up, Sir.")

    if re.match(r"^(volume down|decrease volume|turn (the )?volume down|quieter)$", t):
        execute_tool("media_volume_down", {})
        return _reply("Turning it down, Sir.")

    # --- Read-only "check X" queries: no reasoning needed, so answer
    # straight from psutil/pycaw/screen_brightness_control instead of
    # spending a Groq round-trip on a number the tool already has. ---
    if re.match(
        r"^(what'?s|what is|check|show|tell me)?\s*(the )?(current )?(ram|memory)"
        r"( usage| use| utilization)?\s*(kitna( use)? ho raha( hai)?|kya hai)?$",
        t,
    ) or re.match(r"^(ram|memory) (usage|use)\s*(check karo|batao|dekho)?$", t):
        r = _parsed("get_cpu_ram_usage")
        if "error" in r:
            return _reply(f"I couldn't read RAM usage, Sir: {r['error']}")
        return _reply(f"RAM is at {r['ram_percent']}% ({r['ram_used']} of {r['ram_total']}), Sir.")

    if re.match(
        r"^(what'?s|what is|check|show|tell me)?\s*(the )?(current )?cpu"
        r"( usage| use| load)?\s*(kitna( use)? ho raha( hai)?|kya hai)?$",
        t,
    ) or re.match(r"^cpu (usage|use|load)\s*(check karo|batao|dekho)?$", t):
        r = _parsed("get_cpu_ram_usage")
        if "error" in r:
            return _reply(f"I couldn't read CPU usage, Sir: {r['error']}")
        return _reply(f"CPU is at {r['cpu_percent']}% across {r['cpu_cores_logical']} logical cores, Sir.")

    if re.match(
        r"^(what'?s|what is|check|show|tell me)?\s*(the )?(current )?disk"
        r"( space| usage)?\s*(kitna (bacha|use ho raha)( hai)?|kya hai)?$",
        t,
    ) or re.match(r"^disk (space|usage)\s*(check karo|batao|dekho)?$", t):
        r = _parsed("get_disk_usage")
        if "error" in r:
            return _reply(f"I couldn't read disk usage, Sir: {r['error']}")
        return _reply(f"Drive {r['drive']} is {r['percent_used']}% full - {r['free']} free of {r['total']}, Sir.")

    if re.match(
        r"^(what'?s|what is|check|show|tell me)?\s*(the )?(current )?volume" r"\s*(kitna (hai|par hai))?$",
        t,
    ) or re.match(r"^volume (level|status)\s*(check karo|batao|dekho)?$", t):
        r = _parsed("get_volume")
        if "error" in r:
            return _reply(f"I couldn't read the volume, Sir: {r['error']}")
        return _reply(f"Volume is at {r['volume']} percent, Sir.")

    if re.match(
        r"^(what'?s|what is|check|show|tell me)?\s*(the )?(current )?brightness" r"\s*(kitna (hai|par hai))?$",
        t,
    ) or re.match(r"^brightness (level|status)\s*(check karo|batao|dekho)?$", t):
        r = _parsed("get_brightness")
        if "error" in r:
            return _reply(f"I couldn't read the brightness, Sir: {r['error']}")
        return _reply(f"Brightness is at {r['brightness']} percent, Sir.")

    if re.match(
        r"^(what'?s|what is|check|show|tell me)?\s*(the )?battery"
        r"\s*(status|level|percentage)?\s*(kitni (hai|bachi hai))?$",
        t,
    ) or re.match(r"^battery (status|level)\s*(check karo|batao|dekho)?$", t):
        r = _parsed("get_battery_status")
        if "error" in r:
            return _reply(f"I couldn't read the battery, Sir: {r['error']}")
        return _reply(f"Battery is at {r['percentage']}%{' and charging' if r['charging'] else ''}, Sir.")

    if re.match(r"^(mute|mute (the )?(volume|audio|sound))$", t):
        execute_tool("mute", {})
        return _reply("Muted, Sir.")

    if re.match(r"^(unmute|unmute (the )?(volume|audio|sound))$", t):
        execute_tool("unmute", {})
        return _reply("Unmuted, Sir.")

    if re.match(r"^(lock( the)? screen|lock (my )?(pc|computer))$", t):
        execute_tool("lock_screen", {})
        return _reply("Locking the screen, Sir.")

    if re.match(r"^(take a screenshot|screenshot|capture (the )?screen)$", t):
        execute_tool("take_screenshot", {})
        return _reply("Screenshot captured, Sir.")

    if re.match(r"^(pause|play|pause music|resume|resume music|play music)$", t):
        execute_tool("media_play_pause", {})
        return _reply("Done, Sir.")

    if re.match(r"^(next( track| song)?|skip( this)?)$", t):
        execute_tool("media_next", {})
        return _reply("Skipping, Sir.")

    if re.match(r"^(previous( track| song)?|go back( a track| a song)?)$", t):
        execute_tool("media_previous", {})
        return _reply("Going back, Sir.")

    m = re.match(r"^open (.+)$", t)
    if m and len(m.group(1)) <= 30 and "http" not in m.group(1) and "www." not in m.group(1):
        app = m.group(1).strip()
        result = execute_tool("open_application", {"app_name": app})
        # Let genuinely failed opens fall through to the LLM, which can
        # reason about what the user might have meant.
        try:
            if json.loads(result).get("success"):
                return _reply(f"Opening {app}, Sir.")
        except (json.JSONDecodeError, AttributeError):
            from core.error_trace import log_swallowed as _lsw

            _lsw("ai.local_router.route_system_command")
        return None

    return None


def route(text: str) -> RouteResult:
    """Single entry point: check control commands, then local system
    commands, and report back whether the LLM still needs to handle it."""
    action = check_control_command(text)
    if action:
        return RouteResult(matched=True, action=action)

    local = route_system_command(text)
    if local:
        return local

    return RouteResult(matched=False)
