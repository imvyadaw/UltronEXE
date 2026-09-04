"""
Scheduler
=========
Provider-agnostic scheduling layer on top of google_calendar.py and
outlook_calendar.py. Picks whichever provider is configured (or both),
so the AI tool layer can just call `schedule_meeting(...)` without
knowing whether the user is on Google or Microsoft.
"""

import datetime
from typing import Dict, List, Optional

from skills.calendar.google_calendar import GoogleCalendarClient
from skills.calendar.outlook_calendar import OutlookCalendarClient


class Scheduler:
    """Routes scheduling requests to whichever calendar backend is configured."""

    def __init__(self, provider: str = "auto"):
        """provider: 'google', 'outlook', or 'auto' (use whichever is configured,
        preferring google if both are)."""
        self.google = GoogleCalendarClient()
        self.outlook = OutlookCalendarClient()
        self.provider = provider

    def _active_client(self):
        if self.provider == "google":
            return self.google, "google"
        if self.provider == "outlook":
            return self.outlook, "outlook"
        if self.google.is_configured():
            return self.google, "google"
        if self.outlook.is_configured():
            return self.outlook, "outlook"
        return None, None

    def schedule_meeting(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
    ) -> Dict:
        client, name = self._active_client()
        if client is None:
            return {"success": False, "error": "No calendar provider configured. Set up Google or Outlook credentials."}
        result = client.create_event(
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
        )
        result["provider"] = name
        return result

    def upcoming_events(self, max_results: int = 10) -> Dict:
        client, name = self._active_client()
        if client is None:
            return {"success": False, "error": "No calendar provider configured."}
        result = client.list_events(max_results=max_results)
        result["provider"] = name
        return result

    def cancel_meeting(self, event_id: str) -> Dict:
        client, name = self._active_client()
        if client is None:
            return {"success": False, "error": "No calendar provider configured."}
        result = client.delete_event(event_id)
        result["provider"] = name
        return result

    def find_common_free_slot(self, date: str, duration_minutes: int = 30) -> Dict:
        """Only meaningful for Google (which has find_free_slots); for Outlook we
        fall back to listing today's events so the caller can eyeball gaps."""
        client, name = self._active_client()
        if client is None:
            return {"success": False, "error": "No calendar provider configured."}
        if name == "google":
            result = client.find_free_slots(date=date, duration_minutes=duration_minutes)
            result["provider"] = name
            return result

        events = client.list_events(max_results=50)
        events["provider"] = name
        events["note"] = "Outlook free-slot math isn't implemented; showing raw events for the day instead."
        return events

    def reschedule(self, event_id: str, new_start: str, new_end: str) -> Dict:
        client, name = self._active_client()
        if client is None:
            return {"success": False, "error": "No calendar provider configured."}
        result = client.update_event(event_id, start_time=new_start, end_time=new_end)
        result["provider"] = name
        return result

    def daily_agenda(self) -> Dict:
        """Convenience wrapper: today's events only, human-readable."""
        client, name = self._active_client()
        if client is None:
            return {"success": False, "error": "No calendar provider configured."}
        today = datetime.date.today().isoformat()
        events = client.list_events(max_results=25)
        if not events.get("success"):
            return events
        todays = [e for e in events["events"] if e["start"][:10] == today]
        return {"success": True, "provider": name, "date": today, "count": len(todays), "events": todays}
