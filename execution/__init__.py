"""
Execution (Phase 24)
=============================
The layer that turns a decision into a real action - as opposed to
Phase 20's intelligence/ packages, which decide *what* to say
(proactive_intelligence/), what to have *ready*
(predictive_preparation/), or how to make a call *fast*
(adaptive_performance/), this package is where ULTRON actually *does*
something on the machine, with automatic recovery wired in:

    app_launcher.py   - logged wrapper over skills/app_control's
                         AppLauncher. Owns table `app_launch_events`.
    auto_player.py    - unified replay of automation/RPA scripts and
                         automation/macro macros. Owns table
                         `playback_events`.
    web_automator.py  - unified web automation: live-browser control
                         (browser/automation) and scripted Selenium
                         sessions (automation/RPA/web_rpa), kept
                         cleanly separate. Owns table
                         `web_automation_events`.
    self_healer.py    - wires a real executor into Phase 19.5's
                         self_healing_engine.py for the first time,
                         so a failed step can actually be retried
                         instead of only diagnosed. Owns table
                         `heal_events`.
    macro_executor.py - single entry point tying all of the above
                         together: execute() runs a mixed sequence of
                         app/playback/web steps in order, healing
                         failures automatically when possible. Owns
                         tables `macro_runs` and `macro_steps`.

Usage:
    from execution import get_macro_executor

    executor = get_macro_executor()
    result = executor.execute([
        {"type": "app_launch", "app_name": "notepad", "wait": True},
        {"type": "rpa_script", "name": "fill_daily_log"},
        {"type": "web_navigate", "action": "refresh"},
    ], macro_name="morning_routine")

Each sub-module also exposes its own get_x() singleton and can be
used directly - e.g. call app_launcher.py alone just to launch and log
one app, with no macro sequencing or healing involved.

Purely additive - nothing in Phase 1-23 imports from here, and none of
app_launcher.py/auto_player.py/web_automator.py reimplement anything
skills/app_control, automation/RPA, automation/macro, or
browser/automation already do; they only wrap, log, and (via
self_healer.py) retry those existing implementations.
"""

from execution.app_launcher import AppLaunchExecutor, get_app_launcher
from execution.auto_player import AutoPlayer, get_auto_player
from execution.web_automator import WebAutomator, get_web_automator
from execution.self_healer import SelfHealer, get_self_healer
from execution.macro_executor import MacroExecutor, get_macro_executor

__all__ = [
    "AppLaunchExecutor",
    "get_app_launcher",
    "AutoPlayer",
    "get_auto_player",
    "WebAutomator",
    "get_web_automator",
    "SelfHealer",
    "get_self_healer",
    "MacroExecutor",
    "get_macro_executor",
]
