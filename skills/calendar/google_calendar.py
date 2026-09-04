"""
Google Calendar skill
======================
Create, list, update, delete Google Calendar events via the Calendar API.
Shares the same OAuth client file as Gmail (skills/email/gmail.py) if you
add the calendar scope there, but keeps its own token cache by default so
the two can be authorized independently.

Setup: same Google Cloud project as Gmail works fine - just enable the
"Google Calendar API" too. Credentials JSON path: GCAL_CREDENTIALS_PATH
(defaults to the same file as Gmail's).
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarClient:
    """Wrapper around the Google Calendar API v3."""

    def __init__(
        self, credentials_path: Optional[str] = None, token_path: Optional[str] = None, calendar_id: str = "primary"
    ):
        self.credentials_path = Path(
            credentials_path
            or os.getenv("GCAL_CREDENTIALS_PATH", BASE_DIR / "storage" / "cache" / "gmail_credentials.json")
        )
        self.token_path = Path(
            token_path or os.getenv("GCAL_TOKEN_PATH", BASE_DIR / "storage" / "cache" / "gcal_token.json")
        )
        self.calendar_id = calendar_id
        self._service = None

    def is_configured(self) -> bool:
        return HAS_GOOGLE and self.credentials_path.exists()

    def _get_service(self):
        if not HAS_GOOGLE:
            raise RuntimeError(
                "Google Calendar support needs: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        if self._service is not None:
            return self._service

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(f"OAuth client not found at {self.credentials_path}")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    # -- CRUD -----------------------------------------------------------
    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
        timezone: str = "Asia/Kolkata",
    ) -> Dict:
        """start_time / end_time in ISO 8601, e.g. '2026-08-05T14:00:00'."""
        try:
            service = self._get_service()
            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"dateTime": start_time, "timeZone": timezone},
                "end": {"dateTime": end_time, "timeZone": timezone},
            }
            if attendees:
                event["attendees"] = [{"email": a} for a in attendees]

            created = service.events().insert(calendarId=self.calendar_id, body=event, sendUpdates="all").execute()
            return {"success": True, "event_id": created["id"], "link": created.get("htmlLink")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_events(self, max_results: int = 10, time_min: Optional[str] = None) -> Dict:
        try:
            import datetime

            service = self._get_service()
            time_min = time_min or datetime.datetime.utcnow().isoformat() + "Z"
            resp = (
                service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = [
                {
                    "id": e["id"],
                    "title": e.get("summary", "(no title)"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "end": e["end"].get("dateTime", e["end"].get("date")),
                    "location": e.get("location", ""),
                }
                for e in resp.get("items", [])
            ]
            return {"success": True, "count": len(events), "events": events}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_event(self, event_id: str, **fields) -> Dict:
        """Pass any of: title, start_time, end_time, description, location."""
        try:
            service = self._get_service()
            event = service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
            if "title" in fields:
                event["summary"] = fields["title"]
            if "description" in fields:
                event["description"] = fields["description"]
            if "location" in fields:
                event["location"] = fields["location"]
            if "start_time" in fields:
                event["start"]["dateTime"] = fields["start_time"]
            if "end_time" in fields:
                event["end"]["dateTime"] = fields["end_time"]

            updated = service.events().update(calendarId=self.calendar_id, eventId=event_id, body=event).execute()
            return {"success": True, "event_id": updated["id"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_event(self, event_id: str) -> Dict:
        try:
            service = self._get_service()
            service.events().delete(calendarId=self.calendar_id, eventId=event_id, sendUpdates="all").execute()
            return {"success": True, "event_id": event_id}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def find_free_slots(
        self, date: str, duration_minutes: int = 30, day_start: str = "09:00", day_end: str = "18:00"
    ) -> Dict:
        """Return free slots on `date` (YYYY-MM-DD) between day_start/day_end."""
        try:
            import datetime

            events = self.list_events(max_results=50, time_min=f"{date}T00:00:00Z")
            if not events["success"]:
                return events

            busy = []
            for e in events["events"]:
                if e["start"][:10] != date:
                    continue
                try:
                    busy.append(
                        (
                            datetime.datetime.fromisoformat(e["start"].replace("Z", "+00:00")),
                            datetime.datetime.fromisoformat(e["end"].replace("Z", "+00:00")),
                        )
                    )
                except ValueError:
                    continue
            busy.sort()

            day_s = datetime.datetime.fromisoformat(f"{date}T{day_start}:00")
            day_e = datetime.datetime.fromisoformat(f"{date}T{day_end}:00")
            free, cursor = [], day_s
            for start, end in busy:
                start = start.replace(tzinfo=None)
                end = end.replace(tzinfo=None)
                if (start - cursor).total_seconds() / 60 >= duration_minutes:
                    free.append((cursor.isoformat(), start.isoformat()))
                cursor = max(cursor, end)
            if (day_e - cursor).total_seconds() / 60 >= duration_minutes:
                free.append((cursor.isoformat(), day_e.isoformat()))

            return {"success": True, "date": date, "free_slots": free}
        except Exception as e:
            return {"success": False, "error": str(e)}
