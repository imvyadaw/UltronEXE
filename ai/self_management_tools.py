"""
Self-management tool wiring
=============================
PHASE_18_9_2_SELF_MANAGEMENT's HEAL/ (health_check, auto_fix, restart,
update_self) and PROACTIVE/ (morning_brief, evening_wrap, health_remind,
meeting_prep, travel_alert) modules are real, fully-implemented, and
already have matching entries in ai/tools_schema.py's TOOLS list (18
tools total: report_component_health, get_overall_health,
suggest_fix_for_component, suggest_fixes_for_failing, log_restart,
get_current_version, add_morning_brief_item, get_morning_brief,
log_evening_event, get_evening_wrap, register_health_reminder,
get_due_health_reminders, acknowledge_health_reminder,
register_meeting_prep, add_meeting_prep_note,
get_upcoming_meetings_with_prep, register_trip, get_travel_alerts) -
but none of them had a ai/tool_runtime.py dispatch entry, so the model
got "Unknown tool" for every one of them despite the backend working
fine. Nothing new here, only wiring - same merge pattern as
ai/utility_tools_wire.py/ai/new_skills_tools.py.
"""

from typing import Dict

_health_check = None
_auto_fix = None
_restart = None
_update_self = None
_morning_brief = None
_evening_wrap = None
_health_remind = None
_meeting_prep = None
_travel_alert = None


def _get_health_check():
    global _health_check
    if _health_check is None:
        from heal.health_check import get_health_check

        _health_check = get_health_check()
    return _health_check


def _get_auto_fix():
    global _auto_fix
    if _auto_fix is None:
        from heal.auto_fix import get_auto_fix

        _auto_fix = get_auto_fix()
    return _auto_fix


def _get_restart():
    global _restart
    if _restart is None:
        from heal.restart import get_restart

        _restart = get_restart()
    return _restart


def _get_update_self():
    global _update_self
    if _update_self is None:
        from heal.update_self import get_update_self

        _update_self = get_update_self()
    return _update_self


def _get_morning_brief():
    global _morning_brief
    if _morning_brief is None:
        from proactive.morning_brief import get_morning_brief

        _morning_brief = get_morning_brief()
    return _morning_brief


def _get_evening_wrap():
    global _evening_wrap
    if _evening_wrap is None:
        from proactive.evening_wrap import get_evening_wrap

        _evening_wrap = get_evening_wrap()
    return _evening_wrap


def _get_health_remind():
    global _health_remind
    if _health_remind is None:
        from proactive.health_remind import get_health_remind

        _health_remind = get_health_remind()
    return _health_remind


def _get_meeting_prep():
    global _meeting_prep
    if _meeting_prep is None:
        from proactive.meeting_prep import get_meeting_prep

        _meeting_prep = get_meeting_prep()
    return _meeting_prep


def _get_travel_alert():
    global _travel_alert
    if _travel_alert is None:
        from proactive.travel_alert import get_travel_alert

        _travel_alert = get_travel_alert()
    return _travel_alert


SELF_MANAGEMENT_DIRECT_HANDLERS: Dict = {
    # -- HEAL ------------------------------------------------------------
    "report_component_health": lambda a: _get_health_check().report(
        a.get("component", ""), a.get("status", ""), a.get("detail", "")
    ),
    "get_overall_health": lambda a: _get_health_check().run_check(),
    "suggest_fix_for_component": lambda a: {
        "component": a.get("component", ""),
        "fixes": _get_auto_fix().suggest_fix(a.get("component", "")),
    },
    "suggest_fixes_for_failing": lambda a: _get_auto_fix().suggest_for_failing(),
    "log_restart": lambda a: _get_restart().request_restart(a.get("component", ""), a.get("reason", "")),
    "get_current_version": lambda a: {"version": _get_update_self().current_version()},
    # -- PROACTIVE ---------------------------------------------------------
    "add_morning_brief_item": lambda a: _get_morning_brief().add_item(
        a.get("section", ""), a.get("text", ""), a.get("priority", 0), a.get("for_date")
    ),
    "get_morning_brief": lambda a: _get_morning_brief().generate_brief(a.get("for_date")),
    "log_evening_event": lambda a: _get_evening_wrap().log_event(
        a.get("text", ""), a.get("kind", "note"), a.get("for_date")
    ),
    "get_evening_wrap": lambda a: _get_evening_wrap().generate_wrap(a.get("for_date")),
    "register_health_reminder": lambda a: _get_health_remind().register_reminder(
        a.get("reminder_id", ""), a.get("label", ""), a.get("interval_hours", 0)
    ),
    "get_due_health_reminders": lambda a: {"due": _get_health_remind().due_reminders()},
    "acknowledge_health_reminder": lambda a: _get_health_remind().acknowledge(a.get("reminder_id", "")),
    "register_meeting_prep": lambda a: _get_meeting_prep().register_meeting(
        a.get("meeting_id", ""), a.get("title", ""), a.get("start_time", 0), a.get("attendees")
    ),
    "add_meeting_prep_note": lambda a: _get_meeting_prep().add_prep_note(a.get("meeting_id", ""), a.get("note", "")),
    "get_upcoming_meetings_with_prep": lambda a: {"meetings": _get_meeting_prep().upcoming(a.get("within_hours", 24))},
    "register_trip": lambda a: _get_travel_alert().register_trip(
        a.get("trip_id", ""), a.get("destination", ""), a.get("depart_time", 0), a.get("mode", "")
    ),
    "get_travel_alerts": lambda a: {"alerts": _get_travel_alert().check_alerts(a.get("within_hours", 24))},
}
