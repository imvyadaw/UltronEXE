"""
Triggers
========
The "is this actually worth interrupting the user for, right now"
layer, sitting between proactive/monitors/ (raw state) and
proactive/personality/ (how to phrase it). Each trigger module owns its
own cooldown/dedupe state so proactive/engine.py's loop can call all
three every tick without worrying about spamming the same alert.

    threshold_alerts.py - CPU/RAM/disk/battery crossing a limit
    time_based.py       - fixed clock-time events (9AM briefing, etc.)
    event_driven.py     - discrete events (app focus change, file change)
"""

from proactive.triggers.threshold_alerts import ThresholdAlerts, get_threshold_alerts
from proactive.triggers.time_based import TimeBasedTriggers, get_time_based_triggers
from proactive.triggers.event_driven import EventDrivenTriggers, get_event_driven_triggers

__all__ = [
    "ThresholdAlerts",
    "get_threshold_alerts",
    "TimeBasedTriggers",
    "get_time_based_triggers",
    "EventDrivenTriggers",
    "get_event_driven_triggers",
]
