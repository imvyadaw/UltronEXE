"""
Ultron phrases
==============
Movie-style line bank for proactive alerts - the thing that makes a
"CPU is at 95%" notification sound like ULTRON said it instead of a
Nagios cron job. Organized by category so tone_manager.py can pick a
category (driven by *what* happened) and a tone (driven by *how urgent*
it is), then format one line with the actual numbers.

Every line takes `**kwargs` via str.format - unused keys are simply
ignored by tone_manager.py's safe formatter, so a line for "battery_low"
doesn't need to worry that a "percent" kwarg wasn't relevant to a
different template in the same category.

This is a static line bank, not a template engine - keep new lines
short (movie one-liners, not paragraphs) and consistent with the
personality already defined in ai/prompts/system_prompts.py (witty,
warm, occasionally "Sir", never a customer-support script).
"""

from typing import Dict, List

# Each category maps to a list of phrase templates. `{name}` is filled in
# where relevant by tone_manager.get_phrase(); str.format placeholders
# that don't have a matching kwarg are left as literal text (handled by
# tone_manager's safe formatter) rather than raising.
PHRASES: Dict[str, List[str]] = {
    # -- greetings / time-based -----------------------------------------
    "morning_briefing": [
        "Good morning, Sir. Systems are green and the day's agenda is ready whenever you are.",
        "Morning, Sir. I've taken the liberty of putting today's briefing together.",
        "Rise and shine. Here's everything you need to know before the coffee kicks in.",
        "Good morning. Shall I walk you through today, or would you like the short version?",
        "Systems online, Sir. Ready to brief you on the day ahead.",
        "Morning. I've been keeping an eye on things since you logged off - here's the rundown.",
        "Another day, Sir. Here's what's waiting for you.",
        "Good morning - I took the liberty of checking your calendar and the weather already.",
        "Top of the morning, Sir. Let's see what today has in store.",
        "Good morning. Everything's in order - here's your briefing.",
    ],
    "evening_wrapup": [
        "Winding down for the day, Sir? Here's how things shook out.",
        "End of day summary, ready whenever you are.",
        "Before you sign off - here's a quick look back at today.",
        "Evening, Sir. Let's tally up the day.",
        "That's a wrap on today. Here's the summary.",
        "Signing off soon? Let me give you the highlights first.",
        "Day's winding down - here's what got done, and what didn't.",
        "Good evening. Quick debrief before you go?",
        "Here's your evening summary, Sir - short and to the point.",
        "Before you close the laptop, a quick word on how today went.",
    ],
    # -- system health ----------------------------------------------------
    "cpu_high": [
        "Sir, CPU load is sitting at {percent}%. Might be worth a look.",
        "I'm reading {percent}% CPU usage - something's working hard.",
        "Processor's under some strain, Sir - {percent}% and climbing.",
        "Just flagging it: CPU's at {percent}%. Shall I show you what's eating it?",
        "Heads up - CPU usage has crossed {percent}%.",
        "We're pushing the processor pretty hard, Sir - {percent}% right now.",
        "CPU's working overtime at {percent}%. Want the top processes?",
        "That's a lot of compute, Sir - {percent}% CPU and holding.",
    ],
    "memory_high": [
        "Memory's getting tight, Sir - {percent}% in use.",
        "We're at {percent}% memory usage. Might want to close a few tabs.",
        "RAM's under pressure - {percent}% and rising.",
        "Just so you know, Sir, memory usage has hit {percent}%.",
        "Getting a bit crowded in there - {percent}% memory used.",
        "Memory's at {percent}%. I can check what's holding onto it, if you like.",
    ],
    "disk_high": [
        "Disk space is running low, Sir - {percent}% full.",
        "You're at {percent}% disk usage. Might be time for a clean-up.",
        "Storage is getting snug - {percent}% full.",
        "Just flagging it: disk usage has reached {percent}%.",
        "We're close to the edge on disk space, Sir - {percent}% used.",
    ],
    "battery_low": [
        "Battery's down to {percent}%, Sir. You may want to plug in soon.",
        "We're at {percent}% battery - worth grabbing the charger.",
        "Power's getting low - {percent}% remaining.",
        "Just a heads up, Sir - {percent}% battery left.",
        "I'd find an outlet before too long, Sir - {percent}% and dropping.",
        "Battery's at {percent}%. Shall I remind you again shortly?",
    ],
    "battery_critical": [
        "Sir, battery's critical - {percent}% left. I'd plug in now, not later.",
        "This is the last call, Sir - {percent}% battery. Please charge soon.",
        "We're nearly out of power - {percent}%. I'd hate to lose progress on anything unsaved.",
        "Battery's about to give out, Sir - {percent}% remaining.",
    ],
    # -- network -----------------------------------------------------------
    "network_down": [
        "We've lost the connection, Sir. I'll keep working locally in the meantime.",
        "Internet's down. I'm switching to local processing until it's back.",
        "Connectivity's dropped - I'll flag you the moment it returns.",
        "Sir, we appear to be offline. Everything still works, just a bit more locally.",
        "No signal at the moment, Sir. I'll manage without it for now.",
    ],
    "network_restored": [
        "We're back online, Sir.",
        "Connection's restored - back to full speed.",
        "Internet's returned. Good as new.",
        "Signal's back, Sir. Cloud services are available again.",
    ],
    # -- activity / breaks ---------------------------------------------
    "idle_break_suggestion": [
        "You've been at it a good while, Sir. A short break wouldn't hurt.",
        "Just a thought - you've been heads-down for {minutes} minutes. Worth stretching your legs.",
        "No pressure, Sir, but you've earned a break after {minutes} minutes straight.",
        "It's been {minutes} minutes without a pause. I'll keep watch if you want to step away.",
        "Might be a good moment for a coffee, Sir - {minutes} minutes and counting.",
    ],
    "welcome_back": [
        "Welcome back, Sir.",
        "Good to see you again.",
        "You're back - anything I can catch you up on?",
        "There you are. Ready when you are.",
    ],
    # -- app / file events --------------------------------------------
    "app_opened": [
        "Noticed you've opened {name}, Sir.",
        "{name} is up and running.",
        "Ah, {name} - back to work, I see.",
        "{name} opened. Let me know if you need anything set up.",
    ],
    "file_changed": [
        "That file just changed, Sir - {name}.",
        "Noticed a change to {name}.",
        "{name} was just modified. Wanted you to know.",
    ],
    # -- meetings ------------------------------------------------------
    "meeting_upcoming": [
        'Sir, "{title}" starts in {minutes} minutes.',
        'Reminder: "{title}" is coming up in {minutes} minutes.',
        'You\'ve got "{title}" in {minutes} minutes - shall I pull anything up for it?',
        'Heads up, Sir - "{title}" begins in {minutes} minutes.',
    ],
    "meeting_starting": [
        '"{title}" is starting now, Sir.',
        'Time for "{title}" - it\'s starting.',
        '"{title}" begins now. Best get in there.',
    ],
    "meeting_ended": [
        '"{title}" has wrapped up, Sir. Shall I note anything down?',
        'That\'s the end of "{title}".',
        '"{title}" is over. Back to the day.',
    ],
    # -- generic acknowledgements / tone fillers ------------------------
    "general_ack": [
        "Understood, Sir.",
        "Noted.",
        "Consider it done.",
        "On it.",
        "Right away, Sir.",
    ],
    "general_positive": [
        "All quiet on the system front, Sir - everything's running smoothly.",
        "Nothing to report - all systems nominal.",
        "Smooth sailing so far today, Sir.",
    ],
    "general_concern": [
        "Something's not quite right, Sir - worth a closer look.",
        "I'd keep an eye on this one.",
        "Not urgent, but I thought you'd want to know.",
    ],
}


def get_phrases(category: str) -> List[str]:
    """All phrase templates for a category, or an empty list if the
    category doesn't exist (caller decides how to handle that, rather
    than this module silently inventing a fallback line)."""
    return PHRASES.get(category, [])


def all_categories() -> List[str]:
    return sorted(PHRASES.keys())
