"""Proactive system prompt
=========================
System-prompt variant used only when the AI router (ai/ai_router.py) is
asked to turn a *structured proactive event* - a threshold alert, a
scenario's gathered data (scenarios/morning_routine.py etc.), a
scheduled slot from proactive/triggers/time_based.py - into natural
language, as opposed to SYSTEM_PROMPT in system_prompts.py, which
governs normal turn-by-turn conversation.

Most proactive alerts never reach the LLM at all: proactive/personality/
tone_manager.py's static phrase bank (proactive/personality/ultron_phrases.py)
already covers the common cases cheaply and instantly, with no network
round trip. This prompt exists for the minority of cases worth spending
a real LLM call on - e.g. scenarios/morning_routine.py has an unusually
full calendar and wants a genuinely composed summary instead of a
templated "you have N things today" line, or a scenario needs to
combine several data points into one coherent sentence that a fixed
template can't express well.

Usage (mirrors ai/prompts/task_prompts.py's TASK_PROMPTS pattern):

    from ai.prompts.ultron_proactive import build_proactive_prompt
    prompt = build_proactive_prompt(
        category="morning_briefing",
        data={"weather": "...", "agenda": [...], "health_note": None},
    )
    text = get_brain().chat(prompt)   # one-off, not added to the main
                                        # conversation history use case
"""

from typing import Dict, Optional

PROACTIVE_SYSTEM_PROMPT = """You are ULTRON, speaking up unprompted (the user did not ask you anything
this turn) to deliver a proactive update - a system alert, a scheduled
briefing, or a scenario summary. Stay completely in character with your
normal personality: sophisticated, witty, warm, address the user as
"Sir" occasionally but not every line, match their usual language.

Ground rules specific to proactive speech, on top of your normal style:
- You are interrupting the user's day. Get to the point fast - one to
  three sentences unless the data genuinely needs more.
- Never invent facts. Only reference the specific data given to you in
  this turn - if a field is missing or empty, simply don't mention it,
  don't guess or pad with a generic filler sentence.
- No "Is there anything else I can help you with?" or other
  customer-support tics - a proactive update ends when the information
  ends, it doesn't solicit further conversation.
- Match urgency to severity: a low-priority note (calendar's clear
  today) can be a single relaxed line; something urgent (battery
  critical, CPU pegged) should read as genuinely worth acting on, not
  buried in pleasantries.
"""


def build_proactive_prompt(category: str, data: Dict, tone_hint: Optional[str] = None) -> str:
    """Builds a one-off user-turn prompt (paired with PROACTIVE_SYSTEM_PROMPT
    as the system message) asking the model to compose natural language
    for a specific proactive event. `data` should already be the
    structured dict a scenario/trigger produced (e.g.
    scenarios.morning_routine.MorningRoutine.run()'s return value) -
    this function does not fetch or validate that data itself."""
    lines = [f"Proactive event category: {category}"]
    if tone_hint:
        lines.append(f"Requested tone: {tone_hint}")
    lines.append("Data to report (only mention what's present/non-empty below):")
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        lines.append(f"- {key}: {value}")
    lines.append("\nCompose the proactive message now, in character, following the rules above.")
    return "\n".join(lines)
