# Calendar skills

| Tool | Module |
|---|---|
| create_event, list_events, update_event, delete_event, find_free_slots | skills/calendar/google_calendar.py (`GoogleCalendarClient`) |
| create_event, list_events, update_event, delete_event | skills/calendar/outlook_calendar.py (`OutlookCalendarClient`) |
| schedule_meeting, upcoming_events, cancel_meeting, find_common_free_slot, reschedule, daily_agenda | skills/calendar/scheduler.py (`Scheduler` - provider-agnostic facade over the two above) |

`Scheduler` auto-picks Google or Outlook based on whichever has valid
credentials configured (`provider="auto"`, override with `"google"` /
`"outlook"`). All AI-callable via ai/new_skills_tools.py.
